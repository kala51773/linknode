import json
import logging
from typing import Any

from wickhunter.common.logger import setup_logger

logger = setup_logger("wickhunter.recovery")

class PersistentEventLog:
    """Write-Ahead-Log (WAL) style persistent event system for recovery and audits."""

    def __init__(self, file_path: str = "data/event_wal.jsonl") -> None:
        self.file_path = file_path

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Atomically append a serialized event to the WAL."""
        import time
        record = {
            "ts": time.time(),
            "type": event_type,
            "payload": payload
        }
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            # We don't want telemetry failures to crash execution, so just log.
            logger.error(f"Failed to write to persistent log: {e}")

    def replay_events(self) -> list[dict[str, Any]]:
        """Read all events from the log for state reconstruction."""
        import os
        if not os.path.exists(self.file_path):
            return []

        events = []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to replay log: {e}")
        return events
