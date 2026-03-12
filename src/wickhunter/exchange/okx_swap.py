import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

import aiohttp
import websockets

from wickhunter.exchange.base import BaseExchangeClient, UnifiedOrder
from wickhunter.exchange.models import NormalizedDepthEvent


@dataclass(slots=True)
class OKXDepthParser:
    """Parses OKX books-l2-tbt payloads into normalized depth events."""

    exchange_name: str = "okx_swap"

    def parse_depth_event(self, payload: str) -> NormalizedDepthEvent:
        raw = json.loads(payload)
        arg = raw.get("arg") or {}

        if arg.get("channel") != "books-l2-tbt":
            raise ValueError("not an OKX books-l2-tbt depth message")

        data = raw.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("missing depth data")

        depth = data[0]
        symbol = str(arg.get("instId", ""))
        seq_id = int(depth.get("seqId", 0))
        prev_seq_id = int(depth.get("prevSeqId", 0))
        event_ts_ms = int(depth.get("ts", 0))

        bids = tuple((float(level[0]), float(level[1])) for level in depth.get("bids", []))
        asks = tuple((float(level[0]), float(level[1])) for level in depth.get("asks", []))

        return NormalizedDepthEvent(
            exchange=self.exchange_name,
            symbol=symbol,
            first_update_id=seq_id,
            final_update_id=seq_id,
            prev_final_update_id=prev_seq_id,
            bids=bids,
            asks=asks,
            event_ts_ms=event_ts_ms,
        )


@dataclass
class OKXSwapClient(BaseExchangeClient):
    """Async client for OKX perpetual swap REST/WS integration."""

    depth_parser: OKXDepthParser
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    rest_url: str = "https://www.okx.com"
    ws_public_url: str = "wss://ws.okx.com:8443/ws/v5/public"
    ws_private_url: str = "wss://ws.okx.com:8443/ws/v5/private"
    is_demo: bool = False
    _session: aiohttp.ClientSession | None = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:  # type: ignore[truthy-function]
            connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session  # type: ignore[return-value]

    async def close_session(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def normalize_depth_payload(self, payload: str) -> NormalizedDepthEvent:
        return self.depth_parser.parse_depth_event(payload)

    async def _public_request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        session = await self.get_session()
        url = f"{self.rest_url}{path}{query}"
        async with session.get(url) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"code": str(resp.status), "msg": await resp.text()}
        return data if isinstance(data, dict) else {"code": "1", "msg": "unexpected response"}

    def _build_signed_headers(self, method: str, path: str, body: str) -> dict[str, str]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        prehash = f"{timestamp}{method.upper()}{path}{body}"
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("utf-8")

        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json",
        }
        if self.is_demo:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _signed_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        sign_path = f"{path}{query}"
        body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
        headers = self._build_signed_headers(method=method, path=sign_path, body=body)

        session = await self.get_session()
        url = f"{self.rest_url}{sign_path}"
        async with session.request(method.upper(), url, headers=headers, data=body or None) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"code": str(resp.status), "msg": await resp.text()}
        return data if isinstance(data, dict) else {"code": "1", "msg": "unexpected response"}

    async def get_orderbook_snapshot(self, symbol: str, limit: int = 400) -> dict[str, Any]:
        return await self._public_request("/api/v5/market/books", params={"instId": symbol, "sz": str(limit)})

    async def get_history_trades(
        self,
        *,
        symbol: str,
        after: str | None = None,
        before: str | None = None,
        pagination_type: str = "2",
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "instId": symbol,
            "type": pagination_type,
            "limit": str(max(1, min(100, limit))),
        }
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return await self._public_request("/api/v5/market/history-trades", params=params)

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = 0.0,
        order_type: str = "LIMIT",
        time_in_force: str = "GTC",
        td_mode: str = "cross",
        pos_side: str | None = None,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        del time_in_force  # Not used by OKX v5 order endpoint.
        ord_type = order_type.lower()
        if ord_type not in {"limit", "market", "post_only", "fok", "ioc"}:
            ord_type = "limit"

        payload: dict[str, Any] = {
            "instId": symbol,
            "tdMode": td_mode,
            "side": side.lower(),
            "ordType": ord_type,
            "sz": str(qty),
        }
        if ord_type == "limit":
            payload["px"] = str(price)
        if pos_side:
            payload["posSide"] = pos_side
        if reduce_only:
            payload["reduceOnly"] = "true"
        if client_order_id:
            payload["clOrdId"] = client_order_id

        return await self._signed_request("POST", "/api/v5/trade/order", payload=payload)

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"instId": symbol}
        if order_id:
            payload["ordId"] = order_id
        elif client_order_id:
            payload["clOrdId"] = client_order_id
        else:
            return {"code": "1", "msg": "missing order_id or client_order_id"}
        return await self._signed_request("POST", "/api/v5/trade/cancel-order", payload=payload)

    async def get_open_orders(self, symbol: str) -> list[UnifiedOrder]:
        response = await self._signed_request(
            "GET",
            "/api/v5/trade/orders-pending",
            params={"instId": symbol},
        )
        data = response.get("data", [])
        if not isinstance(data, list):
            return []
        orders: list[UnifiedOrder] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            orders.append(
                UnifiedOrder(
                    exchange="okx_swap",
                    symbol=str(item.get("instId", symbol)),
                    order_id=str(item.get("ordId", "")),
                    client_order_id=str(item.get("clOrdId", "")),
                    side=str(item.get("side", "")),
                    status=str(item.get("state", "")),
                    price=float(item.get("px", "0") or 0.0),
                    qty=float(item.get("sz", "0") or 0.0),
                    filled_qty=float(item.get("accFillSz", "0") or 0.0),
                )
            )
        return orders

    async def get_order_status(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"instId": symbol}
        if order_id:
            params["ordId"] = order_id
        if client_order_id:
            params["clOrdId"] = client_order_id
        return await self._signed_request("GET", "/api/v5/trade/order", params=params)

    async def get_positions(self, symbol: str) -> dict[str, Any]:
        return await self._signed_request("GET", "/api/v5/account/positions", params={"instId": symbol})

    async def get_net_position_qty(self, symbol: str) -> float:
        positions = await self.get_positions(symbol)
        data = positions.get("data", [])
        if not isinstance(data, list):
            return 0.0
        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("instId", "")) != symbol:
                continue
            raw = item.get("pos", "0")
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    async def close_position_market(
        self,
        *,
        symbol: str,
        qty: float | None = None,
        td_mode: str = "cross",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Best-effort net-mode close helper that mitigates 51169/51170 races under concurrency."""
        target_remaining = abs(qty) if qty is not None else None
        for _ in range(max(1, max_retries)):
            net_pos = await self.get_net_position_qty(symbol)
            if abs(net_pos) <= 0:
                return {
                    "code": "0",
                    "msg": "no_position",
                    "data": [{"sCode": "0", "sMsg": "No position to close", "ordId": "", "clOrdId": ""}],
                }

            close_side = "sell" if net_pos > 0 else "buy"
            close_qty = abs(net_pos) if target_remaining is None else min(abs(net_pos), target_remaining)
            if close_qty <= 0:
                return {
                    "code": "0",
                    "msg": "no_position",
                    "data": [{"sCode": "0", "sMsg": "No position to close", "ordId": "", "clOrdId": ""}],
                }

            response = await self.place_order(
                symbol=symbol,
                side=close_side,
                qty=close_qty,
                order_type="market",
                td_mode=td_mode,
                reduce_only=True,
            )

            row = {}
            data = response.get("data")
            if isinstance(data, list) and data:
                if isinstance(data[0], dict):
                    row = data[0]
            s_code = str(row.get("sCode", ""))
            if response.get("code") == "0" and s_code == "0":
                if target_remaining is not None:
                    new_abs_pos = abs(await self.get_net_position_qty(symbol))
                    reduced = max(0.0, abs(net_pos) - new_abs_pos)
                    target_remaining = max(0.0, target_remaining - reduced)
                    if target_remaining > 0:
                        continue
                return response
            if s_code not in {"51169", "51170"}:
                return response
        return {
            "code": "1",
            "msg": "close_position_retry_exhausted",
            "data": [{"sCode": "51169", "sMsg": "position close retry exhausted"}],
        }

    async def stream_depth(self, symbol: str, callback: Callable[[str], None], speed: str = "") -> None:
        channel = speed or "books-l2-tbt"
        subscribe_msg = json.dumps({"op": "subscribe", "args": [{"channel": channel, "instId": symbol}]})
        async for ws in websockets.connect(self.ws_public_url):
            try:
                await ws.send(subscribe_msg)
                async for message in ws:
                    callback(message)
            except websockets.ConnectionClosed:
                continue
