import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from wickhunter.backtest.pair_backtest import PairBacktestConfig, run_pair_backtest

BASE = "https://fapi.binance.com"


def _get_json(path: str) -> object:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int | None = None, limit: int = 1500):
    out = []
    cur = start_ms
    while True:
        params = f"symbol={symbol}&interval={interval}&limit={limit}&startTime={cur}"
        if end_ms:
            params += f"&endTime={end_ms}"
        data = _get_json(f"/fapi/v1/klines?{params}")
        if not data:
            break
        out.extend(data)
        last_open = int(data[-1][0])
        if last_open == cur:
            break
        cur = last_open + 1
        if len(data) < limit:
            break
        time.sleep(0.04)
    return out


def _series_from_klines(klines) -> pd.Series:
    return pd.Series([float(r[4]) for r in klines], index=[int(r[0]) for r in klines])


def _periods_per_year(interval: str) -> int:
    if interval.endswith("m"):
        mins = int(interval[:-1])
        return int(365 * 24 * 60 / mins)
    if interval.endswith("h"):
        hours = int(interval[:-1])
        return int(365 * 24 / hours)
    if interval.endswith("d"):
        days = int(interval[:-1])
        return int(365 / days)
    return 365


def main() -> None:
    parser = argparse.ArgumentParser(description="Pair backtest using Binance futures klines.")
    parser.add_argument("--a", required=True, help="Hedge symbol A, e.g. ADAUSDT")
    parser.add_argument("--b", required=True, help="Target symbol B, e.g. OGNUSDT")
    parser.add_argument("--interval", default="4h", help="Kline interval: 1d,4h,1h,15m")
    parser.add_argument("--days", type=int, default=365, help="Lookback window in days")
    parser.add_argument("--entry-z", type=float, default=2.0, help="Entry z-score")
    parser.add_argument("--exit-z", type=float, default=0.5, help="Exit z-score")
    parser.add_argument("--fee-bps", type=float, default=4.0, help="Round-trip fee bps per side")
    parser.add_argument("--window", type=int, default=180, help="Rolling window size for z-score")
    args = parser.parse_args()

    a = args.a.upper()
    b = args.b.upper()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(30, int(args.days)))
    start_ms = int(start.timestamp() * 1000)

    k_a = _fetch_klines(a, args.interval, start_ms)
    k_b = _fetch_klines(b, args.interval, start_ms)
    s_a = _series_from_klines(k_a)
    s_b = _series_from_klines(k_b)

    cfg = PairBacktestConfig(
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        fee_bps=args.fee_bps,
        window=args.window,
    )
    report, trades, equity = run_pair_backtest(
        prices_a=s_a,
        prices_b=s_b,
        config=cfg,
        periods_per_year=_periods_per_year(args.interval),
    )

    out_dir = Path("data/backtest_pair")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    trades_file = out_dir / f"{a}_{b}_{args.interval}_trades_{suffix}.csv"
    equity_file = out_dir / f"{a}_{b}_{args.interval}_equity_{suffix}.csv"
    if not trades.empty:
        trades.to_csv(trades_file, index=False)
    if not equity.empty:
        equity.to_csv(equity_file, header=["equity"])

    summary = {
        "pair": f"{a}-{b}",
        "interval": args.interval,
        "bars": len(equity),
        "trades": report.trades,
        "win_rate": report.win_rate,
        "total_pnl": report.total_pnl,
        "avg_pnl": report.avg_pnl,
        "sharpe": report.sharpe,
        "max_drawdown": report.max_drawdown,
        "beta": report.beta,
        "mean_spread": report.mean_spread,
        "spread_std": report.spread_std,
        "trades_file": str(trades_file) if trades_file.exists() else None,
        "equity_file": str(equity_file) if equity_file.exists() else None,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
