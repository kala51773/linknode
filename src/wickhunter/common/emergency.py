import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request


@dataclass(slots=True)
class EmergencyNotifier:
    """Persist emergency events and optionally forward them to a webhook."""

    log_path: str = ""
    webhook_url: str = ""
    webhook_timeout_seconds: float = 2.0

    def notify(self, *, event_type: str, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        record = {"event_type": event_type, "payload": payload}

        if self.log_path:
            try:
                path = Path(self.log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"log_write_failed:{exc}")

        if self.webhook_url:
            try:
                body = json.dumps(record).encode("utf-8")
                req = request.Request(
                    self.webhook_url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(req, timeout=self.webhook_timeout_seconds) as resp:
                    status = getattr(resp, "status", 200)
                if status >= 400:
                    errors.append(f"webhook_http_{status}")
            except Exception as exc:
                errors.append(f"webhook_failed:{exc}")

        return errors
