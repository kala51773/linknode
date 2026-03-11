from dataclasses import dataclass


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
        import os
        testnet = os.getenv(f"{prefix}TESTNET", "false").lower() == "true"
        if testnet:
            return cls(
                api_key=os.getenv(f"{prefix}API_KEY", ""),
                api_secret=os.getenv(f"{prefix}API_SECRET", ""),
                rest_url="https://testnet.binancefuture.com",
                ws_url="wss://testnet.binancefuture.com/ws",
                testnet=True
            )
        return cls(
            api_key=os.getenv(f"{prefix}API_KEY", ""),
            api_secret=os.getenv(f"{prefix}API_SECRET", ""),
            rest_url="https://fapi.binance.com",
            ws_url="wss://fstream.binance.com/ws",
            testnet=False
        )


@dataclass(slots=True)
class RiskLimits:
    """Hard limits based on the V1 PRD baseline."""

    daily_loss_limit_pct: float = 2.0
    strategy_drawdown_stop_pct: float = 5.0
    max_events_per_day: int = 20
    max_naked_b_exposure_seconds: float = 1.0
