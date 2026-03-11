import unittest

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


if __name__ == "__main__":
    unittest.main()
