"""Backtest components for replay and lightweight simulation."""

from wickhunter.backtest.replay import EventReplayer, ReplayEvent
from wickhunter.backtest.runner import BacktestResult, BacktestRunner
from wickhunter.backtest.depth_replay import DepthReplayResult, run_depth_replay_jsonl
from wickhunter.backtest.l2_convert import DepthConvertStats, convert_binance_depth_jsonl_to_replay
from wickhunter.backtest.l2_runner import L2BacktestResult, run_l2_backtest_jsonl
from wickhunter.backtest.l2_data import (
    BinanceDepthSnapshot,
    fetch_binance_futures_depth_snapshot,
    fetch_binance_futures_depth_snapshot_with_fallback,
    save_snapshot_as_replay_jsonl,
)

__all__ = [
    "ReplayEvent",
    "EventReplayer",
    "BacktestResult",
    "BacktestRunner",
    "DepthReplayResult",
    "run_depth_replay_jsonl",
    "DepthConvertStats",
    "convert_binance_depth_jsonl_to_replay",
    "L2BacktestResult",
    "run_l2_backtest_jsonl",
    "BinanceDepthSnapshot",
    "fetch_binance_futures_depth_snapshot",
    "fetch_binance_futures_depth_snapshot_with_fallback",
    "save_snapshot_as_replay_jsonl",
]
