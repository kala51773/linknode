import argparse

from wickhunter.analytics.report import EventPnL, build_event_report
from wickhunter.backtest.replay import EventReplayer, ReplayEvent
from wickhunter.common.config import RiskLimits, TradingConfig
from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import NautilusTraderAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.bridge import BinanceSignalBridge, OKXSignalBridge
from wickhunter.exchange.okx_swap import OKXDepthParser, OKXSwapClient
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.execution.throttle import CancelThrottle
from wickhunter.marketdata.calculators import MicrostructureMetrics
from wickhunter.marketdata.orderbook import DepthUpdate, LocalOrderBook
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.portfolio.position import Fill as PositionFill, Portfolio
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine
from wickhunter.strategy.state_machine import EngineState, StrategyState
from wickhunter.simulation.hedge_latency import HedgeLatencyModel
from wickhunter.runtime import WickHunterRuntime
from wickhunter.backtest.l2_simulator import (
    create_default_l2_simulator,
    optimize_l2_simulator,
)
from pathlib import Path


def run_demo() -> str:
    config = TradingConfig()
    risk = RiskLimits()
    state = EngineState()

    state.transition(StrategyState.ARM)
    state.transition(StrategyState.QUOTE)
    state.transition(StrategyState.FILL_B)
    state.transition(StrategyState.HEDGE_A)

    return (
        f"WickHunter booted with {config.primary_exchange}->{config.secondary_exchange}, "
        f"replay={config.replay_engine}, daily_loss_limit={risk.daily_loss_limit_pct}%, "
        f"state={state.current.value}"
    )


def run_book_demo() -> str:
    book = LocalOrderBook()
    book.load_snapshot(
        last_update_id=100,
        bids=((100.0, 2.0), (99.5, 3.0)),
        asks=((100.5, 1.5), (101.0, 4.0)),
    )
    book.apply(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 1.0),), asks=()))
    book.apply(DepthUpdate(first_update_id=102, final_update_id=102, prev_final_update_id=101, bids=(), asks=((100.5, 0.0),)))

    return f"best_bid={book.best_bid}, best_ask={book.best_ask}, mid={book.mid_price}"


def run_sync_demo() -> str:
    sync = BookSynchronizer()
    sync.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 1.0),)))
    sync.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((101.0, 2.0),)))
    sync.apply_snapshot(last_update_id=100, bids=((99.0, 1.0),), asks=((101.5, 1.0),))
    return f"synced={sync.is_synced}, best_bid={sync.book.best_bid}, best_ask={sync.book.best_ask}"


def run_quote_demo() -> str:
    engine = QuoteEngine(max_name_risk=2_000)
    armed, reason = engine.should_arm(
        metrics=MicrostructureMetrics(spread_bps=12.0, depth_5bp_bid=30.0, depth_10bp_bid=50.0),
        baseline_depth_5bp=100.0,
    )
    plan = engine.build_plan(fair_price=100.0, armed=armed, reason=reason)
    return f"armed={plan.armed}, levels={len(plan.levels)}, reason={plan.reason}"


def run_signal_demo() -> str:
    engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 30.0),)))
    engine.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((100.1, 5.0),)))
    engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))
    plan = engine.generate_quote_plan(fair_price=100.0)
    return f"armed={plan.armed}, levels={len(plan.levels)}, reason={plan.reason}"


def run_mature_demo() -> str:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    signal_engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 30.0),)))
    signal_engine.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((100.1, 5.0),)))
    signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

    orchestrator = CoreOrchestrator(
        signal_engine=signal_engine,
        execution_engine=ExecutionEngine(
            risk_checker=RiskChecker(RiskLimits()),
            hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0),
        ),
        backend=NautilusTraderAdapter(),
    )

    result = orchestrator.on_market_and_fill(
        fair_price=100.0,
        fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
        risk_state=RuntimeRiskState(daily_loss_pct=0.1, events_today=1, naked_b_exposure_seconds=0.2),
        hedge_reference_price=50_000,
    )

    hedge_ok = result.hedge_submit.accepted if result.hedge_submit else False
    return f"backend=nautilus_trader, quote_ok={result.quote_submit.accepted}, hedge_ok={hedge_ok}"


def run_exchange_demo() -> str:
    payload = (
        '{"e":"depthUpdate","E":1700000000000,"s":"BTCUSDT","U":100,"u":102,"pu":101,'
        '"b":[["50000.1","1.2"]],"a":[["50001.0","2.5"]]}'
    )
    client = BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser())
    event = client.normalize_depth_payload(payload)
    return (
        f"exchange={event.exchange}, symbol={event.symbol}, "
        f"update=[{event.first_update_id},{event.final_update_id}]"
    )


def run_exchange_signal_demo() -> str:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    client = BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser())

    p1 = '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}'
    p2 = '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}'

    signal_engine.on_normalized_depth_event(client.normalize_depth_payload(p1))
    signal_engine.on_normalized_depth_event(client.normalize_depth_payload(p2))
    signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

    plan = signal_engine.generate_quote_plan(fair_price=100.0)
    return f"source=binance_normalized, armed={plan.armed}, levels={len(plan.levels)}"


def run_okx_exchange_demo() -> str:
    payload = (
        '{"arg":{"channel":"books-l2-tbt","instId":"BTC-USDT-SWAP"},"action":"update","data":['
        '{"bids":[["50000.1","1.2","0","1"]],"asks":[["50001.0","2.5","0","1"]],'
        '"ts":"1700000000000","seqId":1001,"prevSeqId":1000}]}'
    )
    client = OKXSwapClient(depth_parser=OKXDepthParser())
    event = client.normalize_depth_payload(payload)
    return (
        f"exchange={event.exchange}, symbol={event.symbol}, "
        f"update=[{event.first_update_id},{event.final_update_id}]"
    )


def run_okx_exchange_signal_demo() -> str:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    bridge = OKXSignalBridge(
        client=OKXSwapClient(depth_parser=OKXDepthParser()),
        signal_engine=signal_engine,
    )

    payloads = [
        '{"arg":{"channel":"books-l2-tbt","instId":"BTC-USDT-SWAP"},"action":"update","data":[{"bids":[["100.0","30.0","0","1"]],"asks":[],"ts":"1","seqId":101,"prevSeqId":100}]}',
        '{"arg":{"channel":"books-l2-tbt","instId":"BTC-USDT-SWAP"},"action":"update","data":[{"bids":[],"asks":[["100.1","5.0","0","1"]],"ts":"2","seqId":102,"prevSeqId":101}]}',
    ]
    count = bridge.ingest_many(payloads)
    signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

    plan = signal_engine.generate_quote_plan(fair_price=100.0)
    return f"source=okx_normalized, ingested={count}, armed={plan.armed}, levels={len(plan.levels)}"


def run_m3_demo() -> str:
    events = [
        ReplayEvent(ts_ms=1005, event_type="fill", payload={"qty": 2, "px": 100.0}),
        ReplayEvent(ts_ms=1001, event_type="fill", payload={"qty": 1, "px": 99.8}),
    ]
    ordered = EventReplayer(events).run()

    latency_model = HedgeLatencyModel(base_latency_ms=20, latency_per_notional_ms=0.01)
    hedge_results = [latency_model.simulate(hedge_notional=1000.0), latency_model.simulate(hedge_notional=2500.0)]

    report = build_event_report(
        pnls=[EventPnL(gross_pnl=12.0, fees=1.2, funding=0.3), EventPnL(gross_pnl=-2.0, fees=0.5, funding=0.0)],
        hedge_results=hedge_results,
    )

    return (
        f"m3_events={len(ordered)}, first_ts={ordered[0].ts_ms}, "
        f"net_pnl={report.total_net_pnl}, avg_latency={report.avg_hedge_latency_ms}"
    )




def run_m3_replay_file(path: str) -> str:
    ordered = EventReplayer.from_jsonl(path).run()
    if not ordered:
        return "m3_events=0, first_ts=na, last_ts=na"
    return f"m3_events={len(ordered)}, first_ts={ordered[0].ts_ms}, last_ts={ordered[-1].ts_ms}"

def run_bridge_demo() -> str:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    bridge = BinanceSignalBridge(
        client=BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser()),
        signal_engine=signal_engine,
    )

    payloads = [
        '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}',
        '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}',
    ]
    count = bridge.ingest_many(payloads)
    signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))
    plan = signal_engine.generate_quote_plan(fair_price=100.0)

    return f"bridge_ingested={count}, armed={plan.armed}, levels={len(plan.levels)}"


def run_portfolio_demo() -> str:
    portfolio = Portfolio()
    portfolio.on_fill(PositionFill(symbol="BTCUSDT", side="BUY", qty=0.1, price=50_000.0))
    portfolio.on_fill(PositionFill(symbol="ETHUSDT", side="SELL", qty=1.0, price=3_000.0))
    gross = portfolio.gross_notional({"BTCUSDT": 51_000.0, "ETHUSDT": 2_900.0})
    return f"positions={len(portfolio.positions)}, gross_notional={gross}"


def run_runtime_demo() -> str:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )
    runtime = WickHunterRuntime(
        bridge=BinanceSignalBridge(
            client=BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser()),
            signal_engine=signal_engine,
        ),
        orchestrator=CoreOrchestrator(
            signal_engine=signal_engine,
            execution_engine=ExecutionEngine(
                risk_checker=RiskChecker(RiskLimits()),
                hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0),
            ),
            backend=NautilusTraderAdapter(),
        ),
    )

    runtime.on_market_payloads([
        '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}',
        '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}',
    ])
    runtime.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

    result = runtime.step(
        fair_price=100.0,
        fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
        risk_state=RuntimeRiskState(daily_loss_pct=0.1, events_today=1, naked_b_exposure_seconds=0.2),
        hedge_reference_price=50_000,
        marketdata_latency_ms=40,
        consecutive_hedge_failures=0,
        exchange_restricted=False,
    )

    return f"runtime_ok={result.accepted}, quote={result.quote_submitted}, hedge={result.hedge_submitted}"


def run_exec_demo() -> str:
    risk_checker = RiskChecker(RiskLimits())
    hedge_manager = HedgeManager(hedge_symbol="BTCUSDT", beta_exec=0.8)
    engine = ExecutionEngine(risk_checker=risk_checker, hedge_manager=hedge_manager)

    fill = FillEvent(symbol="ALTUSDT", qty=10.0, price=5.0)
    runtime = RuntimeRiskState(daily_loss_pct=0.2, events_today=1, naked_b_exposure_seconds=0.5)
    result = engine.on_b_fill(fill=fill, state=runtime, reference_price=50_000.0)

    return f"accepted={result.accepted}, reason={result.reason}, hedge={result.hedge_order}"


def run_cancel_demo() -> str:
    engine = ExecutionEngine(
        risk_checker=RiskChecker(RiskLimits()),
        hedge_manager=HedgeManager(hedge_symbol="BTCUSDT"),
        cancel_throttle=CancelThrottle(max_cancels_per_window=1, window_seconds=5.0, min_order_live_seconds=0.5),
    )

    decisions = [
        engine.request_cancel(now=10.2, order_created_at=10.0),
        engine.request_cancel(now=10.8, order_created_at=10.0),
        engine.request_cancel(now=11.0, order_created_at=10.0),
    ]
    return f"d1={decisions[0].reason}, d2={decisions[1].reason}, d3={decisions[2].reason}"


def run_l2_real_demo() -> str:
    from pathlib import Path
    path = Path("data/real_l2_events.jsonl")
    if not path.exists():
        return f"File {path} not found. Run scripts/collect_real_l2_data.py first."
    tuned = optimize_l2_simulator(file_path=path, min_events=20)
    if tuned is None:
        simulator = create_default_l2_simulator()
        report = simulator.run(path)
        return (
            f"l2_real_events={report.event_count}, net_pnl={report.total_net_pnl:.6f}, "
            f"avg_hedge_latency={report.avg_hedge_latency_ms:.1f}ms, avg_slippage={report.avg_slippage_bps:.2f}bps"
        )

    cfg = tuned.config
    report = tuned.report
    return (
        f"l2_real_events={report.event_count}, net_pnl={report.total_net_pnl:.6f}, "
        f"avg_hedge_latency={report.avg_hedge_latency_ms:.1f}ms, avg_slippage={report.avg_slippage_bps:.2f}bps, "
        f"theta1={cfg.theta1:.8f}, theta2={cfg.theta2:.8f}, theta3={cfg.theta3:.8f}, baseline={cfg.baseline_depth_5bp:.0f}"
    )


def run_discover_demo() -> str:
    import numpy as np
    import pandas as pd

    from wickhunter.strategy.discover import DiscoverConfig, DiscoverEngine
    from wickhunter.strategy.pair_selector import PairSelector
    from wickhunter.strategy.universe import UniverseManager

    idx = pd.RangeIndex(start=0, stop=900, step=1)
    base = np.exp(np.linspace(10.0, 10.35, len(idx)) + 0.003 * np.sin(np.arange(len(idx)) / 12))
    b_good = base * np.exp(0.002 * np.sin(np.arange(len(idx)) / 6))
    b_too_liquid = base * np.exp(0.0025 * np.sin(np.arange(len(idx)) / 8))
    b_low_corr = np.exp(np.linspace(10.4, 10.0, len(idx)) + 0.08 * np.sin(np.arange(len(idx)) / 3))

    history = {
        "BTCUSDT": {
            "1d": pd.Series(base, index=idx),
            "4h": pd.Series(base[::2], index=idx[::2]),
        },
        "ALT1USDT": {
            "1d": pd.Series(b_good, index=idx),
            "4h": pd.Series(b_good[::2], index=idx[::2]),
        },
        "ALT2USDT": {
            "1d": pd.Series(b_too_liquid, index=idx),
            "4h": pd.Series(b_too_liquid[::2], index=idx[::2]),
        },
        "ALT3USDT": {
            "1d": pd.Series(b_low_corr, index=idx),
            "4h": pd.Series(b_low_corr[::2], index=idx[::2]),
        },
    }
    raw_markets = [
        {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "quoteVolume": 3_000_000_000},
        {"symbol": "ALT1USDT", "baseAsset": "ALT1", "quoteAsset": "USDT", "quoteVolume": 120_000_000},
        {"symbol": "ALT2USDT", "baseAsset": "ALT2", "quoteAsset": "USDT", "quoteVolume": 1_100_000_000},
        {"symbol": "ALT3USDT", "baseAsset": "ALT3", "quoteAsset": "USDT", "quoteVolume": 100_000_000},
    ]

    discover = DiscoverEngine(universe=UniverseManager(), selector=PairSelector())
    result = discover.run_auto_discovery_multi_tf(
        raw_markets=raw_markets,
        price_history_by_tf=history,
        config=DiscoverConfig(
            anchor_symbols=("BTCUSDT",),
            min_daily_volume_usd=50_000_000,
            max_daily_volume_usd=500_000_000,
            min_history_points=300,
            min_history_points_by_tf={"1d": 300, "4h": 300},
            timeframes=("1d", "4h"),
            timeframe_weights={"1d": 0.65, "4h": 0.35},
            top_k=3,
        ),
    )
    if not result:
        return "discover_pairs=0"
    best = result[0]
    return (
        f"discover_pairs={len(result)}, best_a={best.pair_a}, best_b={best.pair_b}, score={best.score:.4f}, "
        f"corr={best.components.get('corr_30d', 0.0):.3f}, r2={best.components.get('r2_6h', 0.0):.3f}, "
        f"vol_ratio={best.components.get('volume_ratio_b_to_a', 0.0):.3f}"
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="WickHunter dev CLI")
    parser.add_argument("--demo", action="store_true", help="Run state-machine demo flow")
    parser.add_argument("--book-demo", action="store_true", help="Run local orderbook synchronization demo")
    parser.add_argument("--sync-demo", action="store_true", help="Run buffered snapshot synchronization demo")
    parser.add_argument("--quote-demo", action="store_true", help="Run quote planning demo")
    parser.add_argument("--signal-demo", action="store_true", help="Run end-to-end signal generation demo")
    parser.add_argument("--mature-demo", action="store_true", help="Run mature-engine orchestration demo")
    parser.add_argument("--exchange-demo", action="store_true", help="Run exchange parser normalization demo")
    parser.add_argument("--exchange-signal-demo", action="store_true", help="Run normalized exchange -> signal pipeline demo")
    parser.add_argument("--okx-exchange-demo", action="store_true", help="Run OKX parser normalization demo")
    parser.add_argument("--okx-exchange-signal-demo", action="store_true", help="Run OKX normalized exchange -> signal pipeline demo")
    parser.add_argument("--m3-demo", action="store_true", help="Run M3 replay/simulation/report demo")
    parser.add_argument("--replay-file", type=str, default=None, help="Replay events from JSONL file")
    parser.add_argument("--bridge-demo", action="store_true", help="Run exchange bridge -> signal demo")
    parser.add_argument("--portfolio-demo", action="store_true", help="Run portfolio position tracking demo")
    parser.add_argument("--runtime-demo", action="store_true", help="Run runtime wiring demo")
    parser.add_argument("--exec-demo", action="store_true", help="Run execution orchestration demo")
    parser.add_argument("--cancel-demo", action="store_true", help="Run cancel throttle demo")
    parser.add_argument("--l2-real-demo", action="store_true", help="Run L2 simulator on real data collected from Binance")
    parser.add_argument("--discover-demo", action="store_true", help="Run automatic B-symbol discovery demo")
    args = parser.parse_args()

    if args.demo:
        print(run_demo())
    elif args.book_demo:
        print(run_book_demo())
    elif args.sync_demo:
        print(run_sync_demo())
    elif args.quote_demo:
        print(run_quote_demo())
    elif args.signal_demo:
        print(run_signal_demo())
    elif args.mature_demo:
        print(run_mature_demo())
    elif args.exchange_demo:
        print(run_exchange_demo())
    elif args.exchange_signal_demo:
        print(run_exchange_signal_demo())
    elif args.okx_exchange_demo:
        print(run_okx_exchange_demo())
    elif args.okx_exchange_signal_demo:
        print(run_okx_exchange_signal_demo())
    elif args.m3_demo:
        print(run_m3_demo())
    elif args.replay_file:
        print(run_m3_replay_file(args.replay_file))
    elif args.bridge_demo:
        print(run_bridge_demo())
    elif args.portfolio_demo:
        print(run_portfolio_demo())
    elif args.runtime_demo:
        print(run_runtime_demo())
    elif args.exec_demo:
        print(run_exec_demo())
    elif args.cancel_demo:
        print(run_cancel_demo())
    elif args.l2_real_demo:
        print(run_l2_real_demo())
    elif args.discover_demo:
        print(run_discover_demo())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
