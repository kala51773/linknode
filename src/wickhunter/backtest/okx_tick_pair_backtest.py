from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class OKXTradeTick:
    symbol: str
    ts_ms: int
    price: float
    size: float
    side: str
    trade_id: str


@dataclass(slots=True)
class OKXTickPairBacktestConfig:
    entry_z: float = 4.0
    exit_z: float = 1.5
    fee_bps: float = 5.0
    warmup_ticks: int = 2_000
    z_window: int = 1_000
    max_hold_ticks: int = 5_000
    allow_long: bool = True
    allow_short: bool = True


@dataclass(slots=True)
class OKXTickPairBacktestReport:
    ticks: int
    trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    sharpe: float
    max_drawdown: float
    beta: float
    mean_spread: float
    spread_std: float


def _estimate_beta(log_a: pd.Series, log_b: pd.Series) -> float:
    var_a = float(np.var(log_a))
    if var_a <= 0:
        return 1.0
    return float(np.cov(log_a, log_b)[0, 1] / var_a)


def build_tick_price_frame(
    *,
    symbol_a: str,
    symbol_b: str,
    trades_a: list[OKXTradeTick],
    trades_b: list[OKXTradeTick],
) -> pd.DataFrame:
    rows = (
        [{"ts_ms": t.ts_ms, "symbol": symbol_a, "price": t.price, "size": t.size, "side": t.side, "trade_id": t.trade_id} for t in trades_a]
        + [{"ts_ms": t.ts_ms, "symbol": symbol_b, "price": t.price, "size": t.size, "side": t.side, "trade_id": t.trade_id} for t in trades_b]
    )
    if not rows:
        return pd.DataFrame(columns=["ts_ms", "price_a", "price_b", "active_symbol", "size", "side", "trade_id"])

    frame = pd.DataFrame(rows).sort_values(["ts_ms", "trade_id", "symbol"]).reset_index(drop=True)
    frame["price_a"] = np.where(frame["symbol"] == symbol_a, frame["price"], np.nan)
    frame["price_b"] = np.where(frame["symbol"] == symbol_b, frame["price"], np.nan)
    frame["price_a"] = frame["price_a"].ffill()
    frame["price_b"] = frame["price_b"].ffill()
    frame = frame.dropna(subset=["price_a", "price_b"]).reset_index(drop=True)
    frame = frame.rename(columns={"symbol": "active_symbol"})
    return frame[["ts_ms", "price_a", "price_b", "active_symbol", "size", "side", "trade_id"]]


def run_okx_tick_pair_backtest(
    *,
    symbol_a: str,
    symbol_b: str,
    trades_a: list[OKXTradeTick],
    trades_b: list[OKXTradeTick],
    config: OKXTickPairBacktestConfig,
    periods_per_year: int,
) -> tuple[OKXTickPairBacktestReport, pd.DataFrame, pd.Series]:
    frame = build_tick_price_frame(symbol_a=symbol_a, symbol_b=symbol_b, trades_a=trades_a, trades_b=trades_b)
    if frame.shape[0] <= max(config.warmup_ticks, config.z_window) + 5:
        empty = pd.DataFrame(columns=["entry_ts", "exit_ts", "side", "entry_z", "exit_z", "hold_ticks", "pnl"])
        report = OKXTickPairBacktestReport(
            ticks=int(frame.shape[0]),
            trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            avg_pnl=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            beta=1.0,
            mean_spread=0.0,
            spread_std=0.0,
        )
        return report, empty, pd.Series(dtype=float)

    log_a = np.log(frame["price_a"].astype(float))
    log_b = np.log(frame["price_b"].astype(float))
    beta = _estimate_beta(log_a.iloc[: config.warmup_ticks], log_b.iloc[: config.warmup_ticks])
    spread = log_b - beta * log_a

    rolling_mean = spread.rolling(config.z_window).mean()
    rolling_std = spread.rolling(config.z_window).std()
    z = (spread - rolling_mean) / rolling_std

    ret_a = frame["price_a"].pct_change().fillna(0.0)
    ret_b = frame["price_b"].pct_change().fillna(0.0)
    fee_per_side = (config.fee_bps / 10_000.0) * (1 + abs(beta))

    position = 0
    entry_idx: int | None = None
    entry_z = 0.0
    entry_spread = 0.0
    entry_equity = 0.0
    equity_value = 0.0
    equity_points: list[float] = []
    equity_index: list[int] = []
    trades: list[dict[str, float | int | str]] = []

    start_idx = max(config.warmup_ticks, config.z_window)
    for idx in range(start_idx, len(frame)):
        z_val = float(z.iloc[idx])
        if not np.isfinite(z_val):
            continue

        if position == 0:
            if config.allow_long and z_val <= -config.entry_z:
                position = 1
                entry_idx = idx
                entry_z = z_val
                entry_spread = float(spread.iloc[idx])
                entry_equity = equity_value
                equity_value -= fee_per_side
            elif config.allow_short and z_val >= config.entry_z:
                position = -1
                entry_idx = idx
                entry_z = z_val
                entry_spread = float(spread.iloc[idx])
                entry_equity = equity_value
                equity_value -= fee_per_side

        if position != 0 and entry_idx is not None:
            step_pnl = position * (float(ret_b.iloc[idx]) - beta * float(ret_a.iloc[idx]))
            equity_value += step_pnl

            hold_ticks = idx - entry_idx
            exit_long = position == 1 and z_val >= -config.exit_z
            exit_short = position == -1 and z_val <= config.exit_z
            exit_timeout = hold_ticks >= config.max_hold_ticks
            if exit_long or exit_short or exit_timeout:
                equity_value -= fee_per_side
                trades.append(
                    {
                        "entry_ts": int(frame.iloc[entry_idx]["ts_ms"]),
                        "exit_ts": int(frame.iloc[idx]["ts_ms"]),
                        "side": "LONG_SPREAD" if position == 1 else "SHORT_SPREAD",
                        "entry_z": float(entry_z),
                        "exit_z": z_val,
                        "entry_spread": entry_spread,
                        "exit_spread": float(spread.iloc[idx]),
                        "hold_ticks": int(hold_ticks),
                        "pnl": float(equity_value - entry_equity),
                        "exit_reason": "timeout" if exit_timeout and not (exit_long or exit_short) else "mean_revert",
                    }
                )
                position = 0
                entry_idx = None

        equity_points.append(equity_value)
        equity_index.append(int(frame.iloc[idx]["ts_ms"]))

    trades_df = pd.DataFrame(trades)
    equity_series = pd.Series(equity_points, index=equity_index, dtype=float)
    if trades_df.empty:
        win_rate = 0.0
        avg_pnl = 0.0
    else:
        win_rate = float((trades_df["pnl"] > 0).mean())
        avg_pnl = float(trades_df["pnl"].mean())

    if equity_series.empty:
        sharpe = 0.0
        max_drawdown = 0.0
    else:
        returns = equity_series.diff().fillna(0.0)
        if float(returns.std()) > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))
        else:
            sharpe = 0.0
        running_max = equity_series.cummax()
        max_drawdown = float((equity_series - running_max).min())

    report = OKXTickPairBacktestReport(
        ticks=int(frame.shape[0]),
        trades=int(trades_df.shape[0]),
        win_rate=round(win_rate, 4),
        total_pnl=float(equity_value),
        avg_pnl=round(avg_pnl, 6),
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_drawdown, 6),
        beta=round(beta, 6),
        mean_spread=round(float(spread.mean()), 6),
        spread_std=round(float(spread.std()), 6),
    )
    return report, trades_df, equity_series
