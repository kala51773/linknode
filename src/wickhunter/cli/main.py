import argparse

from wickhunter.analytics.report import EventPnL, build_event_report
from wickhunter.backtest.replay import EventReplayer, ReplayEvent
from wickhunter.backtest.runner import BacktestRunner
from wickhunter.backtest.depth_replay import run_depth_replay_jsonl
from wickhunter.backtest.l2_convert import convert_binance_depth_jsonl_to_replay
from wickhunter.backtest.l2_runner import run_l2_backtest_jsonl
from wickhunter.backtest.l2_data import (
    fetch_binance_futures_depth_snapshot_with_fallback,
    save_snapshot_as_replay_jsonl,
)
from wickhunter.common.config import RiskLimits, TradingConfig
from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import NautilusTraderAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.bridge import BinanceSignalBridge
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
    book.apply(DepthUpdate(first_update_id=101, final_update_id=101, bids=((100.0, 1.0),), asks=()))
    book.apply(DepthUpdate(first_update_id=102, final_update_id=102, bids=(), asks=((100.5, 0.0),)))

    return f"best_bid={book.best_bid}, best_ask={book.best_ask}, mid={book.mid_price}"


def run_sync_demo() -> str:
    sync = BookSynchronizer()
    sync.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, bids=((100.0, 1.0),)))
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
    engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, bids=((100.0, 30.0),)))
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
    signal_engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, bids=((100.0, 30.0),)))
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
        '{"e":"depthUpdate","E":1700000000000,"s":"BTCUSDT","U":100,"u":102,'
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

    p1 = '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[["100.0","30.0"]],"a":[]}'
    p2 = '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"b":[],"a":[["100.1","5.0"]]}'

    signal_engine.on_normalized_depth_event(client.normalize_depth_payload(p1))
    signal_engine.on_normalized_depth_event(client.normalize_depth_payload(p2))
    signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

    plan = signal_engine.generate_quote_plan(fair_price=100.0)
    return f"source=binance_normalized, armed={plan.armed}, levels={len(plan.levels)}"


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



def run_backtest_file(path: str, *, strict: bool = True) -> str:
    result = BacktestRunner().run_jsonl(path, strict=strict)
    pf = "na" if result.profit_factor is None else str(result.profit_factor)
    return (
        f"events={result.event_count}, fills={result.fill_count}, skipped_fills={result.skipped_fill_count}, "
        f"skipped_ratio={result.skipped_fill_ratio}, net_pnl={result.total_net_pnl}, "
        f"avg_net={result.avg_net_pnl}, avg_latency={result.avg_hedge_latency_ms}, "
        f"avg_slippage={result.avg_slippage_bps}, win_rate={result.win_rate}, "
        f"max_dd={result.max_drawdown}, profit_factor={pf}"
    )



def run_download_l2_snapshot(symbol: str, output_path: str, *, base_url: str = "https://fapi.binance.com") -> str:
    base_candidates = (base_url, "https://fapi1.binance.com", "https://fapi2.binance.com", "https://fapi3.binance.com")
    deduped = tuple(dict.fromkeys(base_candidates))
    snapshot = fetch_binance_futures_depth_snapshot_with_fallback(symbol, base_urls=deduped)
    saved = save_snapshot_as_replay_jsonl(snapshot, output_path)
    return (
        f"snapshot_saved={saved}, symbol={snapshot.symbol}, "
        f"last_update_id={snapshot.last_update_id}, bids={len(snapshot.bids)}, asks={len(snapshot.asks)}, "
        f"source={snapshot.source_url}"
    )



def run_convert_depth_jsonl(input_path: str, output_path: str, *, strict: bool = True) -> str:
    stats = convert_binance_depth_jsonl_to_replay(input_path, output_path, strict=strict)
    return (
        f"converted_total={stats.total_lines}, written={stats.written_events}, skipped={stats.skipped_lines}, "
        f"output={output_path}"
    )



def run_l2_backtest_file(path: str, *, strict: bool = True) -> str:
    result = run_l2_backtest_jsonl(path, strict=strict)
    return (
        f"events={result.total_events}, depth_events={result.depth_events}, snapshots={result.snapshot_events}, "
        f"updates={result.update_events}, skipped={result.skipped_events}, ignored_non_depth={result.ignored_non_depth_events}, "
        f"gaps={result.gap_events}, avg_spread_bps={result.avg_spread_bps}, avg_depth_5bp={result.avg_depth_5bp_bid}, "
        f"avg_depth_10bp={result.avg_depth_10bp_bid}, avg_mid_move_bps={result.avg_mid_move_bps}, "
        f"last_update_id={result.last_update_id}, best_bid={result.best_bid}, best_ask={result.best_ask}"
    )


def run_replay_depth_file(path: str, *, strict: bool = True) -> str:
    result = run_depth_replay_jsonl(path, strict=strict)
    return (
        f"events={result.total_events}, snapshots={result.snapshot_events}, updates={result.update_events}, "
        f"skipped={result.skipped_events}, ignored_non_depth={result.ignored_non_depth_events}, gaps={result.gap_events}, last_update_id={result.last_update_id}, "
        f"best_bid={result.best_bid}, best_ask={result.best_ask}, mid={result.mid_price}"
    )

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
        '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[["100.0","30.0"]],"a":[]}',
        '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"b":[],"a":[["100.1","5.0"]]}',
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
        '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[["100.0","30.0"]],"a":[]}',
        '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"b":[],"a":[["100.1","5.0"]]}',
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
    parser.add_argument("--m3-demo", action="store_true", help="Run M3 replay/simulation/report demo")
    parser.add_argument("--replay-file", type=str, default=None, help="Replay events from JSONL file")
    parser.add_argument("--backtest-file", type=str, default=None, help="Backtest fill events from JSONL file")
    parser.add_argument("--backtest-lenient", action="store_true", help="Skip invalid fill payloads during backtest")
    parser.add_argument("--download-l2-snapshot", type=str, default=None, help="Download Binance futures L2 snapshot by symbol")
    parser.add_argument("--snapshot-out", type=str, default="data/l2_snapshot.jsonl", help="Output JSONL path for downloaded L2 snapshot")
    parser.add_argument("--l2-base-url", type=str, default="https://fapi.binance.com", help="Base URL for L2 snapshot download")
    parser.add_argument("--convert-depth-jsonl", type=str, default=None, help="Convert raw Binance depth JSONL into replay JSONL")
    parser.add_argument("--convert-out", type=str, default="data/replay_depth.jsonl", help="Output JSONL path for converted depth replay")
    parser.add_argument("--convert-lenient", action="store_true", help="Skip invalid depth rows during conversion")
    parser.add_argument("--replay-depth-file", type=str, default=None, help="Replay normalized depth JSONL into local book")
    parser.add_argument("--l2-backtest-file", type=str, default=None, help="Run microstructure backtest on normalized depth JSONL")
    parser.add_argument("--replay-depth-lenient", action="store_true", help="Skip invalid/gap depth events during replay")
    parser.add_argument("--l2-backtest-lenient", action="store_true", help="Skip invalid/gap depth events during L2 backtest")
    parser.add_argument("--bridge-demo", action="store_true", help="Run exchange bridge -> signal demo")
    parser.add_argument("--portfolio-demo", action="store_true", help="Run portfolio position tracking demo")
    parser.add_argument("--runtime-demo", action="store_true", help="Run runtime wiring demo")
    parser.add_argument("--exec-demo", action="store_true", help="Run execution orchestration demo")
    parser.add_argument("--cancel-demo", action="store_true", help="Run cancel throttle demo")
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
    elif args.m3_demo:
        print(run_m3_demo())
    elif args.replay_file:
        print(run_m3_replay_file(args.replay_file))
    elif args.backtest_file:
        print(run_backtest_file(args.backtest_file, strict=not args.backtest_lenient))
    elif args.download_l2_snapshot:
        print(run_download_l2_snapshot(args.download_l2_snapshot, args.snapshot_out, base_url=args.l2_base_url))
    elif args.convert_depth_jsonl:
        print(run_convert_depth_jsonl(args.convert_depth_jsonl, args.convert_out, strict=not args.convert_lenient))
    elif args.replay_depth_file:
        print(run_replay_depth_file(args.replay_depth_file, strict=not args.replay_depth_lenient))
    elif args.l2_backtest_file:
        print(run_l2_backtest_file(args.l2_backtest_file, strict=not args.l2_backtest_lenient))
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
