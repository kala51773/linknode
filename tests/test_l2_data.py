import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from wickhunter.backtest.l2_data import (
    BinanceDepthSnapshot,
    fetch_binance_futures_depth_snapshot,
    save_snapshot_as_replay_jsonl,
)


class _MockResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestL2Data(unittest.TestCase):
    @patch("wickhunter.backtest.l2_data.urlopen")
    def test_fetch_binance_futures_depth_snapshot(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _MockResponse(
            {
                "lastUpdateId": 123,
                "bids": [["100.1", "1.5"]],
                "asks": [["100.2", "2.5"]],
            }
        )

        snapshot = fetch_binance_futures_depth_snapshot("btcusdt")

        self.assertEqual(snapshot.symbol, "BTCUSDT")
        self.assertEqual(snapshot.last_update_id, 123)
        self.assertEqual(snapshot.bids, ((100.1, 1.5),))
        self.assertEqual(snapshot.asks, ((100.2, 2.5),))


    @patch("wickhunter.backtest.l2_data.urlopen")
    def test_fetch_http_error_is_wrapped(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = HTTPError(url="u", code=451, msg="blocked", hdrs=None, fp=None)
        with self.assertRaises(RuntimeError):
            fetch_binance_futures_depth_snapshot("BTCUSDT")

    def test_save_snapshot_as_replay_jsonl(self) -> None:
        snapshot = BinanceDepthSnapshot(
            symbol="BTCUSDT",
            last_update_id=999,
            bids=((100.0, 1.0),),
            asks=((100.1, 2.0),),
        )

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "l2.jsonl"
            path = save_snapshot_as_replay_jsonl(snapshot, out)
            self.assertEqual(path, out)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["event_type"], "depth_snapshot")
            self.assertEqual(row["payload"]["symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
