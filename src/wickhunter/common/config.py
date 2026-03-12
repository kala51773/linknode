import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TradingConfig:
    """Top-level runtime config for early-stage development."""

    primary_exchange: str = "binance_futures"
    secondary_exchange: str = "okx_swap"
    replay_engine: str = "nautilus_trader"
    discover_interval_minutes: int = 30
    marketdata_latency_kill_ms: int = 250


@dataclass(slots=True)
class ExchangeConfig:
    """Config for exchange connection, allowing environment-based secrets and URL selection."""
    api_key: str = ""
    api_secret: str = ""
    rest_url: str = "https://fapi.binance.com"
    ws_url: str = "wss://fstream.binance.com/ws"
    testnet: bool = False

    @classmethod
    def from_env(cls, prefix: str = "BINANCE_") -> "ExchangeConfig":
        _load_dotenv_if_present()
        testnet = os.getenv(f"{prefix}TESTNET", "false").lower() == "true"
        rest_url_override = os.getenv(f"{prefix}REST_URL")
        ws_url_override = os.getenv(f"{prefix}WS_URL")
        if testnet:
            return cls(
                api_key=os.getenv(f"{prefix}API_KEY", ""),
                api_secret=os.getenv(f"{prefix}API_SECRET", ""),
                rest_url=rest_url_override or "https://demo-fapi.binance.com",
                ws_url=ws_url_override or "wss://fstream.binancefuture.com/ws",
                testnet=True
            )
        return cls(
            api_key=os.getenv(f"{prefix}API_KEY", ""),
            api_secret=os.getenv(f"{prefix}API_SECRET", ""),
            rest_url=rest_url_override or "https://fapi.binance.com",
            ws_url=ws_url_override or "wss://fstream.binance.com/ws",
            testnet=False
        )


_DOTENV_LOADED = False


def _load_dotenv_if_present() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.exists():
        _load_key_values_into_env(env_path)

    _DOTENV_LOADED = True


def _load_key_values_into_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class RiskLimits:
    """Hard limits based on the V1 PRD baseline."""

    daily_loss_limit_pct: float = 2.0
    strategy_drawdown_stop_pct: float = 5.0
    max_events_per_day: int = 20
    max_naked_b_exposure_seconds: float = 1.0
    min_available_balance_ratio: float = 0.05
    min_wallet_balance_usdt: float = 50.0


@dataclass(slots=True)
class OKXConfig:
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    rest_url: str = "https://www.okx.com"
    ws_public_url: str = "wss://ws.okx.com:8443/ws/v5/public"
    ws_private_url: str = "wss://ws.okx.com:8443/ws/v5/private"
    demo: bool = False

    @classmethod
    def from_env(cls, prefix: str = "OKX_") -> "OKXConfig":
        _load_dotenv_if_present()
        demo = os.getenv(f"{prefix}DEMO", "false").lower() == "true"
        rest_url = os.getenv(f"{prefix}REST_URL")
        ws_public = os.getenv(f"{prefix}WS_PUBLIC_URL")
        ws_private = os.getenv(f"{prefix}WS_PRIVATE_URL")

        if demo:
            return cls(
                api_key=os.getenv(f"{prefix}API_KEY", ""),
                api_secret=os.getenv(f"{prefix}API_SECRET", ""),
                api_passphrase=os.getenv(f"{prefix}API_PASSPHRASE", ""),
                rest_url=rest_url or "https://www.okx.com",
                ws_public_url=ws_public or "wss://wspap.okx.com:8443/ws/v5/public",
                ws_private_url=ws_private or "wss://wspap.okx.com:8443/ws/v5/private",
                demo=True,
            )

        return cls(
            api_key=os.getenv(f"{prefix}API_KEY", ""),
            api_secret=os.getenv(f"{prefix}API_SECRET", ""),
            api_passphrase=os.getenv(f"{prefix}API_PASSPHRASE", ""),
            rest_url=rest_url or "https://www.okx.com",
            ws_public_url=ws_public or "wss://ws.okx.com:8443/ws/v5/public",
            ws_private_url=ws_private or "wss://ws.okx.com:8443/ws/v5/private",
            demo=False,
        )
