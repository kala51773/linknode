from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class PairBacktestConfig:
    entry_z: float = 2.0
    exit_z: float = 0.5
    fee_bps: float = 4.0
    window: int = 180
    allow_long: bool = True
    allow_short: bool = True


@dataclass(slots=True)
class PairBacktestReport:
    trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    sharpe: float
    max_drawdown: float
    beta: float
    mean_spread: float
    spread_std: float


def _compute_beta(log_a: pd.Series, log_b: pd.Series) -> float:
    var_a = float(np.var(log_a))
    if var_a <= 0:
        return 1.0
    return float(np.cov(log_a, log_b)[0, 1] / var_a)


def run_pair_backtest(
    *,
    prices_a: pd.Series,
    prices_b: pd.Series,
    config: PairBacktestConfig,
    periods_per_year: int,
) -> tuple[PairBacktestReport, pd.DataFrame, pd.Series]:
    df = pd.DataFrame({"A": prices_a, "B": prices_b}).dropna()
    df = df[(df["A"] > 0) & (df["B"] > 0)]
    if df.shape[0] <= config.window + 5:
        empty = pd.DataFrame(columns=["entry_ts", "exit_ts", "side", "pnl"])
        report = PairBacktestReport(
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

    log_a = np.log(df["A"])
    log_b = np.log(df["B"])
    beta = _compute_beta(log_a, log_b)
    spread = log_b - beta * log_a

    rolling_mean = spread.rolling(config.window).mean()
    rolling_std = spread.rolling(config.window).std()
    z = (spread - rolling_mean) / rolling_std

    position = 0  # 1 long spread, -1 short spread
    entry_ts = None
    entry_spread = 0.0
    trades = []
    equity = []
    equity_ts = []
    equity_value = 0.0

    returns_a = df["A"].pct_change().fillna(0.0)
    returns_b = df["B"].pct_change().fillna(0.0)

    fee_per_side = (config.fee_bps / 10000.0) * (1 + abs(beta))

    for ts in df.index[config.window:]:
        z_val = z.loc[ts]
        if not np.isfinite(z_val):
            continue

        if position == 0:
            if config.allow_long and z_val <= -config.entry_z:
                position = 1
                entry_ts = ts
                entry_spread = spread.loc[ts]
                equity_value -= fee_per_side
            elif config.allow_short and z_val >= config.entry_z:
                position = -1
                entry_ts = ts
                entry_spread = spread.loc[ts]
                equity_value -= fee_per_side

        if position != 0:
            step_pnl = position * (returns_b.loc[ts] - beta * returns_a.loc[ts])
            equity_value += step_pnl

            exit_long = position == 1 and z_val >= -config.exit_z
            exit_short = position == -1 and z_val <= config.exit_z
            if exit_long or exit_short:
                equity_value -= fee_per_side
                trades.append(
                    {
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "side": "LONG_SPREAD" if position == 1 else "SHORT_SPREAD",
                        "entry_spread": float(entry_spread),
                        "exit_spread": float(spread.loc[ts]),
                        "pnl": float(equity_value),
                    }
                )
                position = 0
                entry_ts = None
                entry_spread = 0.0

        equity.append(equity_value)
        equity_ts.append(ts)

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        win_rate = 0.0
        avg_pnl = 0.0
    else:
        win_rate = float((trades_df["pnl"] > 0).mean())
        avg_pnl = float(trades_df["pnl"].mean())

    equity_series = pd.Series(equity, index=equity_ts, dtype=float)
    if equity_series.empty:
        sharpe = 0.0
        max_dd = 0.0
    else:
        returns = equity_series.diff().fillna(0.0)
        if returns.std() > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))
        else:
            sharpe = 0.0
        running_max = equity_series.cummax()
        drawdown = equity_series - running_max
        max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    report = PairBacktestReport(
        trades=int(trades_df.shape[0]),
        win_rate=round(win_rate, 4),
        total_pnl=float(equity_value),
        avg_pnl=round(avg_pnl, 6),
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd, 6),
        beta=round(beta, 6),
        mean_spread=round(float(spread.mean()), 6),
        spread_std=round(float(spread.std()), 6),
    )
    return report, trades_df, equity_series
