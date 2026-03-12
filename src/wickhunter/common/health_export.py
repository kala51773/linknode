import json
from pathlib import Path


def format_prometheus_snapshot(snapshot: dict[str, object]) -> str:
    lines = []
    for key, value in snapshot.items():
        metric_name = f"wickhunter_live_{key}"
        if isinstance(value, bool):
            lines.append(f"{metric_name} {1 if value else 0}")
        elif isinstance(value, (int, float)):
            lines.append(f"{metric_name} {value}")
    return "\n".join(lines) + "\n"


class HealthExporter:
    def __init__(self, path: str, fmt: str) -> None:
        self.path = Path(path)
        self.format = fmt
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_snapshot(self, snapshot: dict[str, object]) -> None:
        if self.format == "prometheus":
            self.path.write_text(format_prometheus_snapshot(snapshot), encoding="utf-8")
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=True) + "\n")
