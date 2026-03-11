import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    ts_ms: int
    event_type: str
    payload: dict


@dataclass(slots=True)
class EventReplayer:
    """Simple event-driven replay loop for deterministic research runs."""

    events: list[ReplayEvent]

    def run(self) -> list[ReplayEvent]:
        return sorted(self.events, key=lambda e: e.ts_ms)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "EventReplayer":
        events: list[ReplayEvent] = []
        file_path = Path(path)

        with file_path.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue

                data = json.loads(line)
                ts_ms = data.get("ts_ms")
                event_type = data.get("event_type")
                payload = data.get("payload", {})

                if not isinstance(ts_ms, int):
                    raise ValueError(f"line {line_no}: ts_ms must be int")
                if not isinstance(event_type, str) or not event_type:
                    raise ValueError(f"line {line_no}: event_type must be non-empty str")
                if not isinstance(payload, dict):
                    raise ValueError(f"line {line_no}: payload must be dict")

                events.append(ReplayEvent(ts_ms=ts_ms, event_type=event_type, payload=payload))

        return cls(events=events)
