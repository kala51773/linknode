import json
import unittest
from pathlib import Path
from uuid import uuid4

from wickhunter.common.health_export import HealthExporter, format_prometheus_snapshot


class TestHealthExport(unittest.TestCase):
    def test_format_prometheus_snapshot_numeric_and_bool(self) -> None:
        text = format_prometheus_snapshot({"ts_ms": 1, "halted": True, "note": "x"})
        self.assertIn("wickhunter_live_ts_ms 1", text)
        self.assertIn("wickhunter_live_halted 1", text)
        self.assertNotIn("wickhunter_live_note", text)

    def test_jsonl_exporter_appends_lines(self) -> None:
        path = Path(__file__).parent / f"tmp_health_{uuid4().hex}.jsonl"
        try:
            exporter = HealthExporter(str(path), "jsonl")
            exporter.write_snapshot({"ts_ms": 1, "halted": False})
            exporter.write_snapshot({"ts_ms": 2, "halted": True})

            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["ts_ms"], 1)
            self.assertEqual(json.loads(lines[1])["halted"], True)
        finally:
            path.unlink(missing_ok=True)

    def test_prometheus_exporter_overwrites_file(self) -> None:
        path = Path(__file__).parent / f"tmp_health_{uuid4().hex}.prom"
        try:
            exporter = HealthExporter(str(path), "prometheus")
            exporter.write_snapshot({"ts_ms": 1, "halted": False})
            exporter.write_snapshot({"ts_ms": 2, "halted": True})

            content = path.read_text(encoding="utf-8")
            self.assertIn("wickhunter_live_ts_ms 2", content)
            self.assertNotIn("wickhunter_live_ts_ms 1", content)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
