import asyncio
import unittest
from typing import Any

from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser


class TestBinanceFuturesDepthParser(unittest.TestCase):
    def test_parse_depth_event(self) -> None:
        payload = (
            '{"e":"depthUpdate","E":1700000000000,"s":"BTCUSDT","U":100,"u":102,"pu":101,'
            '"b":[["50000.1","1.2"],["50000.0","0"]],"a":[["50001.0","2.5"]]}'
        )

        parser = BinanceFuturesDepthParser()
        event = parser.parse_depth_event(payload)

        self.assertEqual(event.exchange, "binance_futures")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.first_update_id, 100)
        self.assertEqual(event.final_update_id, 102)
        self.assertEqual(event.event_ts_ms, 1700000000000)
        self.assertEqual(event.bids[0], (50000.1, 1.2))
        self.assertEqual(event.asks[0], (50001.0, 2.5))

    def test_client_wraps_parser(self) -> None:
        payload = '{"e":"depthUpdate","E":1,"s":"ETHUSDT","U":7,"u":8,"b":[],"a":[]}'
        client = BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser())

        event = client.normalize_depth_payload(payload)

        self.assertEqual(event.symbol, "ETHUSDT")
        self.assertEqual(event.first_update_id, 7)
        self.assertEqual(event.final_update_id, 8)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.delete_calls: list[dict[str, Any]] = []

    def delete(self, url: str, headers: dict[str, Any]) -> _FakeResponse:
        self.delete_calls.append({"url": url, "headers": headers})
        return _FakeResponse({"code": 0, "msg": "ok"})


class TestBinanceFuturesClient(unittest.TestCase):
    def test_cancel_all_open_orders_calls_rest_endpoint(self) -> None:
        client = BinanceFuturesClient(
            depth_parser=BinanceFuturesDepthParser(),
            api_key="k",
            api_secret="s",
            rest_url="https://fapi.binance.com",
        )
        fake_session = _FakeSession()
        client._session = fake_session  # type: ignore[assignment]

        payload = asyncio.run(client.cancel_all_open_orders("btcusdt"))

        self.assertEqual(payload["code"], 0)
        self.assertEqual(len(fake_session.delete_calls), 1)
        call = fake_session.delete_calls[0]
        self.assertIn("/fapi/v1/allOpenOrders?", call["url"])
        self.assertIn("symbol=BTCUSDT", call["url"])
        self.assertIn("signature=", call["url"])
        self.assertEqual(call["headers"]["X-MBX-APIKEY"], "k")


if __name__ == "__main__":
    unittest.main()
