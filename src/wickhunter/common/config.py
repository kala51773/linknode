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
class RiskLimits:
    """Hard limits based on the V1 PRD baseline."""

    daily_loss_limit_pct: float = 2.0
    strategy_drawdown_stop_pct: float = 5.0
    max_events_per_day: int = 20
    max_naked_b_exposure_seconds: float = 1.0
