import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from wickhunter.backtest.okx_tick_pair_backtest import (
    OKXTickPairBacktestConfig,
    OKXTradeTick,
    run_okx_tick_pair_backtest,
)
from wickhunter.exchange.okx_swap import OKXDepthParser, OKXSwapClient


def _trade_from_row(symbol: str, row: dict) -> OKXTradeTick | None:
    trade_id = str(row.get("tradeId", ""))
    px = row.get("px")
    sz = row.get("sz")
    side = str(row.get("side", ""))
    ts = row.get("ts")
    try:
        if not trade_id or px is None or sz is None or ts is None:
            return None
        return OKXTradeTick(
            symbol=symbol,
            ts_ms=int(ts),
            price=float(px),
            size=float(sz),
            side=side,
            trade_id=trade_id,
        )
    except (TypeError, ValueError):
        return None


async def fetch_history_trades(
    *,
    client: OKXSwapClient,
    symbol: str,
    start_ts_ms: int,
    max_pages: int,
) -> list[OKXTradeTick]:
    trades: list[OKXTradeTick] = []
    after: str | None = None
    seen_ids: set[str] = set()

    for _ in range(max(1, max_pages)):
        payload = await client.get_history_trades(symbol=symbol, after=after, pagination_type="1", limit=100)
        data = payload.get("data", [])
        if not isinstance(data, list) or not data:
            break

        batch: list[OKXTradeTick] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            tick = _trade_from_row(symbol, row)
            if tick is None or tick.trade_id in seen_ids:
                continue
            seen_ids.add(tick.trade_id)
            batch.append(tick)

        if not batch:
            break

        trades.extend(batch)
        oldest = min(batch, key=lambda item: item.ts_ms)
        if oldest.ts_ms <= start_ts_ms:
            break
        oldest_trade = min(batch, key=lambda item: int(item.trade_id))
        after = oldest_trade.trade_id

    trades = [item for item in trades if item.ts_ms >= start_ts_ms]
    trades.sort(key=lambda item: (item.ts_ms, item.trade_id))
    return trades


def _periods_per_year() -> int:
    return 365 * 24 * 60 * 6


async def _run(args: argparse.Namespace) -> dict:
    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(days=max(1, min(90, args.days)))
    start_ts_ms = int(start_ts.timestamp() * 1000)

    client = OKXSwapClient(depth_parser=OKXDepthParser())
    try:
        trades_a, trades_b = await asyncio.gather(
            fetch_history_trades(client=client, symbol=args.a, start_ts_ms=start_ts_ms, max_pages=args.max_pages),
            fetch_history_trades(client=client, symbol=args.b, start_ts_ms=start_ts_ms, max_pages=args.max_pages),
        )
    finally:
        await client.close_session()

    config = OKXTickPairBacktestConfig(
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        fee_bps=args.fee_bps,
        warmup_ticks=args.warmup_ticks,
        z_window=args.z_window,
        max_hold_ticks=args.max_hold_ticks,
    )
    report, trades_df, equity = run_okx_tick_pair_backtest(
        symbol_a=args.a,
        symbol_b=args.b,
        trades_a=trades_a,
        trades_b=trades_b,
        config=config,
        periods_per_year=_periods_per_year(),
    )

    out_dir = Path("data/okx_tick_backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    trades_file = out_dir / f"{args.a}_{args.b}_tick_trades_{suffix}.csv"
    equity_file = out_dir / f"{args.a}_{args.b}_tick_equity_{suffix}.csv"
    if not trades_df.empty:
        trades_df.to_csv(trades_file, index=False)
    if not equity.empty:
        equity.to_csv(equity_file, header=["equity"])

    return {
        "pair": f"{args.a}-{args.b}",
        "days": args.days,
        "ticks_a": len(trades_a),
        "ticks_b": len(trades_b),
        "ticks_merged": report.ticks,
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tick-level pair backtest using OKX history trades.")
    parser.add_argument("--a", required=True, help="A instrument id, e.g. ADA-USDT-SWAP")
    parser.add_argument("--b", required=True, help="B instrument id, e.g. OGN-USDT-SWAP")
    parser.add_argument("--days", type=int, default=30, help="Lookback days, capped at 90 by OKX history trades")
    parser.add_argument("--entry-z", type=float, default=4.0, help="Entry z-score")
    parser.add_argument("--exit-z", type=float, default=1.5, help="Exit z-score")
    parser.add_argument("--fee-bps", type=float, default=5.0, help="Per-side fee bps on pair notional")
    parser.add_argument("--warmup-ticks", type=int, default=2000, help="Ticks for beta warmup")
    parser.add_argument("--z-window", type=int, default=1000, help="Rolling tick window for z-score")
    parser.add_argument("--max-hold-ticks", type=int, default=5000, help="Max ticks to hold a trade")
    parser.add_argument("--max-pages", type=int, default=200, help="Max OKX history-trade pages per symbol")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
