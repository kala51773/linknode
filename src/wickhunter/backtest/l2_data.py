import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class BinanceDepthSnapshot:
    symbol: str
    last_update_id: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]


def fetch_binance_futures_depth_snapshot(
    symbol: str,
    *,
    limit: int = 1000,
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 10.0,
) -> BinanceDepthSnapshot:
    query = urlencode({"symbol": symbol.upper(), "limit": int(limit)})
    url = f"{base_url}/fapi/v1/depth?{query}"
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # network/geo/remote policy path
        raise RuntimeError(f"failed to download L2 snapshot: HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"failed to download L2 snapshot: {exc.reason}") from exc

    return BinanceDepthSnapshot(
        symbol=symbol.upper(),
        last_update_id=int(raw["lastUpdateId"]),
        bids=tuple((float(px), float(qty)) for px, qty in raw.get("bids", [])),
        asks=tuple((float(px), float(qty)) for px, qty in raw.get("asks", [])),
    )


def save_snapshot_as_replay_jsonl(snapshot: BinanceDepthSnapshot, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "ts_ms": 0,
        "event_type": "depth_snapshot",
        "payload": {
            "exchange": "binance_futures",
            "symbol": snapshot.symbol,
            "last_update_id": snapshot.last_update_id,
            "bids": snapshot.bids,
            "asks": snapshot.asks,
        },
    }
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
