import json
from json import JSONDecodeError
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
    source_url: str


def _fetch_from_url(url: str, *, timeout_seconds: float) -> dict:
    with urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_binance_futures_depth_snapshot(
    symbol: str,
    *,
    limit: int = 1000,
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 10.0,
) -> BinanceDepthSnapshot:
    return fetch_binance_futures_depth_snapshot_with_fallback(
        symbol,
        base_urls=(base_url,),
        limit=limit,
        timeout_seconds=timeout_seconds,
    )


def fetch_binance_futures_depth_snapshot_with_fallback(
    symbol: str,
    *,
    base_urls: tuple[str, ...] = (
        "https://fapi.binance.com",
        "https://fapi1.binance.com",
        "https://fapi2.binance.com",
        "https://fapi3.binance.com",
    ),
    limit: int = 1000,
    timeout_seconds: float = 10.0,
) -> BinanceDepthSnapshot:
    if not base_urls:
        raise ValueError("base_urls must not be empty")

    query = urlencode({"symbol": symbol.upper(), "limit": int(limit)})
    errors: list[str] = []

    for base_url in base_urls:
        url = f"{base_url}/fapi/v1/depth?{query}"
        try:
            raw = _fetch_from_url(url, timeout_seconds=timeout_seconds)
            return BinanceDepthSnapshot(
                symbol=symbol.upper(),
                last_update_id=int(raw["lastUpdateId"]),
                bids=tuple((float(px), float(qty)) for px, qty in raw.get("bids", [])),
                asks=tuple((float(px), float(qty)) for px, qty in raw.get("asks", [])),
                source_url=url,
            )
        except HTTPError as exc:
            errors.append(f"{url} -> HTTP {exc.code}")
        except URLError as exc:
            errors.append(f"{url} -> {exc.reason}")
        except JSONDecodeError:
            errors.append(f"{url} -> invalid_json_response")

    raise RuntimeError("failed to download L2 snapshot from all sources: " + "; ".join(errors))


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
            "source_url": snapshot.source_url,
        },
    }
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
