import json
from dataclasses import dataclass

from wickhunter.exchange.models import NormalizedDepthEvent


@dataclass(slots=True)
class BinanceFuturesDepthParser:
    """Parses Binance USDⓈ-M diff-depth payload into normalized event format."""

    exchange_name: str = "binance_futures"

    def parse_depth_event(self, payload: str) -> NormalizedDepthEvent:
        raw = json.loads(payload)

        # Binance futures diff stream fields: e, E, s, U, u, pu, b, a
        symbol = raw["s"]
        first_update_id = int(raw["U"])
        final_update_id = int(raw["u"])
        prev_final_update_id = int(raw.get("pu", 0))
        event_ts_ms = int(raw["E"])

        bids = tuple((float(px), float(qty)) for px, qty in raw.get("b", []))
        asks = tuple((float(px), float(qty)) for px, qty in raw.get("a", []))

        return NormalizedDepthEvent(
            exchange=self.exchange_name,
            symbol=symbol,
            first_update_id=first_update_id,
            final_update_id=final_update_id,
            prev_final_update_id=prev_final_update_id,
            bids=bids,
            asks=asks,
            event_ts_ms=event_ts_ms,
        )


import asyncio
import hmac
import hashlib
import time
from typing import Any, Callable, Optional
import aiohttp
import websockets

@dataclass
class BinanceFuturesClient:
    """Async client for Binance REST/WS integration."""

    depth_parser: BinanceFuturesDepthParser
    api_key: str = ""
    api_secret: str = ""
    rest_url: str = "https://fapi.binance.com"
    ws_url: str = "wss://fstream.binance.com/ws"
    
    _session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:  # type: ignore
            self._session = aiohttp.ClientSession()
        return self._session  # type: ignore

    async def close_session(self) -> None:
        if self._session and not self._session.closed:  # type: ignore
            await self._session.close()  # type: ignore
        self._session = None

    def normalize_depth_payload(self, payload: str) -> NormalizedDepthEvent:
        return self.depth_parser.parse_depth_event(payload)

    def _generate_signature(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def get_orderbook_snapshot(self, symbol: str, limit: int = 1000) -> dict[str, Any]:
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/depth?symbol={symbol.upper()}&limit={limit}"
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = 0.0,
        order_type: str = "LIMIT",
        time_in_force: str = "GTC",
        new_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Place an order (B passive or A IOC)."""
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/order"
        
        timestamp = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(qty),
            "timestamp": str(timestamp),
        }
        if order_type.upper() == "LIMIT":
            params["price"] = str(price)
            params["timeInForce"] = time_in_force.upper()
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
            
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)
        
        headers = {
            "X-MBX-APIKEY": self.api_key
        }
        
        async with session.post(f"{url}?{query_string}&signature={signature}", headers=headers) as resp:
            # We don't raise immediately to handle exchange restriction logic
            data = await resp.json()
        return data

    async def cancel_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/order"
        
        timestamp = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "orderId": str(order_id),
            "timestamp": str(timestamp),
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)
        
        headers = {
            "X-MBX-APIKEY": self.api_key
        }
        
        async with session.delete(f"{url}?{query_string}&signature={signature}", headers=headers) as resp:
            data = await resp.json()
        return data

    async def cancel_all_open_orders(self, symbol: str) -> Any:
        """Cancel all open orders for a symbol."""
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/allOpenOrders"

        timestamp = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(timestamp),
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)

        headers = {
            "X-MBX-APIKEY": self.api_key
        }

    async def get_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch all current open orders for a symbol."""
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/openOrders"
        
        timestamp = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(timestamp),
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)
        
        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.get(f"{url}?{query_string}&signature={signature}", headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data if isinstance(data, list) else []

    async def get_order_status(self, symbol: str, order_id: int | None = None, orig_client_order_id: str | None = None) -> dict[str, Any]:
        """Fetch status of a specific order."""
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/order"
        
        timestamp = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(timestamp),
        }
        if order_id:
            params["orderId"] = str(order_id)
        if orig_client_order_id:
            params["origClientOrderId"] = orig_client_order_id
            
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = self._generate_signature(query_string)
        
        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.get(f"{url}?{query_string}&signature={signature}", headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data

    async def create_listen_key(self) -> str:
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.post(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data["listenKey"]

    async def keepalive_listen_key(self) -> None:
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.put(url, headers=headers) as resp:
            resp.raise_for_status()

    async def delete_listen_key(self) -> None:
        session = await self.get_session()
        url = f"{self.rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.delete(url, headers=headers) as resp:
            resp.raise_for_status()

    async def stream_depth(self, symbol: str, callback: Callable[[str], None], speed: str = "@100ms") -> None:
        stream_name = f"{symbol.lower()}@depth{speed}"
        url = f"{self.ws_url}/{stream_name}"
        
        async for ws in websockets.connect(url):
            try:
                async for message in ws:
                    callback(message)
            except websockets.ConnectionClosed:
                continue

    async def stream_user_data(self, listen_key: str, callback: Callable[[str], None]) -> None:
        """Connects to the User Data Stream using the provided listenKey and feeds messages to the callback."""
        url = f"{self.ws_url}/{listen_key}"
        
        async for ws in websockets.connect(url):
            try:
                async for message in ws:
                    callback(message)
            except websockets.ConnectionClosed:
                # If WS drops, reconnection triggers re-fetching URL (though listenKey itself must be kept alive elsewhere)
                continue
