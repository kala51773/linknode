import unittest
from typing import Any

from wickhunter.exchange.okx_swap import OKXDepthParser, OKXSwapClient


class TestOKXDepthParser(unittest.TestCase):
    def test_parse_depth_event(self) -> None:
        payload = (
            '{"arg":{"channel":"books-l2-tbt","instId":"BTC-USDT-SWAP"},"action":"update","data":['
            '{"bids":[["50000.1","1.2","0","1"]],"asks":[["50001.0","2.5","0","1"]],'
            '"ts":"1700000000000","seqId":1001,"prevSeqId":1000}]}'
        )
        parser = OKXDepthParser()
        event = parser.parse_depth_event(payload)

        self.assertEqual(event.exchange, "okx_swap")
        self.assertEqual(event.symbol, "BTC-USDT-SWAP")
        self.assertEqual(event.first_update_id, 1001)
        self.assertEqual(event.final_update_id, 1001)
        self.assertEqual(event.prev_final_update_id, 1000)
        self.assertEqual(event.bids[0], (50000.1, 1.2))
        self.assertEqual(event.asks[0], (50001.0, 2.5))

    def test_client_wraps_parser(self) -> None:
        payload = (
            '{"arg":{"channel":"books-l2-tbt","instId":"ETH-USDT-SWAP"},"action":"update","data":['
            '{"bids":[],"asks":[],"ts":"1","seqId":7,"prevSeqId":6}]}'
        )
        client = OKXSwapClient(depth_parser=OKXDepthParser())

        event = client.normalize_depth_payload(payload)

        self.assertEqual(event.symbol, "ETH-USDT-SWAP")
        self.assertEqual(event.first_update_id, 7)
        self.assertEqual(event.final_update_id, 7)

    def test_parser_rejects_non_depth_payload(self) -> None:
        parser = OKXDepthParser()
        with self.assertRaises(ValueError):
            parser.parse_depth_event('{"event":"subscribe","arg":{"channel":"books-l2-tbt"}}')


class TestOKXSignedHeaders(unittest.TestCase):
    def test_build_signed_headers_contains_required_fields(self) -> None:
        client = OKXSwapClient(
            depth_parser=OKXDepthParser(),
            api_key="k",
            api_secret="s",
            api_passphrase="p",
            is_demo=True,
        )

        headers = client._build_signed_headers(method="GET", path="/api/v5/account/balance", body="")

        self.assertEqual(headers["OK-ACCESS-KEY"], "k")
        self.assertEqual(headers["OK-ACCESS-PASSPHRASE"], "p")
        self.assertIn("OK-ACCESS-SIGN", headers)
        self.assertIn("OK-ACCESS-TIMESTAMP", headers)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["x-simulated-trading"], "1")


class TestOKXClosePositionHelper(unittest.IsolatedAsyncioTestCase):
    async def test_close_position_market_handles_no_position(self) -> None:
        client = OKXSwapClient(depth_parser=OKXDepthParser())

        async def fake_get_net_position_qty(symbol: str) -> float:
            self.assertEqual(symbol, "BTC-USDT-SWAP")
            return 0.0

        client.get_net_position_qty = fake_get_net_position_qty  # type: ignore[method-assign]

        result = await client.close_position_market(symbol="BTC-USDT-SWAP")
        self.assertEqual(result["code"], "0")
        row = result["data"][0]
        self.assertEqual(row["sCode"], "0")

    async def test_close_position_market_retries_51169_and_succeeds(self) -> None:
        client = OKXSwapClient(depth_parser=OKXDepthParser())
        net_positions = [1.0, 1.0, 0.0]
        responses: list[dict[str, Any]] = [
            {"code": "1", "data": [{"sCode": "51169", "sMsg": "no position in direction"}]},
            {"code": "0", "data": [{"sCode": "0", "sMsg": "ok"}]},
        ]
        calls: list[dict[str, Any]] = []

        async def fake_get_net_position_qty(symbol: str) -> float:
            self.assertEqual(symbol, "BTC-USDT-SWAP")
            return net_positions.pop(0) if net_positions else 0.0

        async def fake_place_order(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return responses.pop(0)

        client.get_net_position_qty = fake_get_net_position_qty  # type: ignore[method-assign]
        client.place_order = fake_place_order  # type: ignore[method-assign]

        result = await client.close_position_market(symbol="BTC-USDT-SWAP", qty=1.0, max_retries=3)

        self.assertEqual(result["code"], "0")
        self.assertEqual(result["data"][0]["sCode"], "0")
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0]["reduce_only"], True)


if __name__ == "__main__":
    unittest.main()
