import asyncio
import argparse
import logging
import time
from wickhunter.common.config import ExchangeConfig, RiskLimits
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.binance_live import BinanceUserDataStream
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.core.mature_engine import BinanceDirectAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.risk.checks import RiskChecker
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.runtime import WickHunterRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live_runner")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live Binance wiring demo.")
    parser.add_argument("--quote-symbol", default="ETHUSDT", help="Name leg symbol.")
    parser.add_argument("--hedge-symbol", default="BTCUSDT", help="Hedge leg symbol.")
    parser.add_argument("--duration-seconds", type=int, default=300, help="Run duration in seconds.")
    parser.add_argument(
        "--skip-user-stream",
        action="store_true",
        help="Skip private user-data stream (market data only).",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    # 1. Config & Client
    ex_config = ExchangeConfig.from_env()
    if not args.skip_user_stream and (not ex_config.api_key or not ex_config.api_secret):
        raise RuntimeError("Missing BINANCE_API_KEY/BINANCE_API_SECRET for live run.")

    client = BinanceFuturesClient(
        depth_parser=BinanceFuturesDepthParser(),
        api_key=ex_config.api_key,
        api_secret=ex_config.api_secret,
        rest_url=ex_config.rest_url,
        ws_url=ex_config.ws_url
    )

    # 2. Strategy Components
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer()
    )
    
    execution_engine = ExecutionEngine(
        risk_checker=RiskChecker(RiskLimits()),
        hedge_manager=HedgeManager(hedge_symbol=args.hedge_symbol.upper(), beta_exec=1.0)
    )
    
    # Recover from log
    execution_engine.recover_state()

    backend = BinanceDirectAdapter(
        client=client,
        quote_symbol=args.quote_symbol.upper(),
        order_tracker=execution_engine._order_tracker # Share tracker for consistency
    )
    
    # Reconcile with exchange
    if not args.skip_user_stream:
        backend.reconcile_open_orders()

    orchestrator = CoreOrchestrator(
        signal_engine=signal_engine,
        execution_engine=execution_engine,
        backend=backend
    )

    runtime = WickHunterRuntime(
        bridge=BinanceSignalBridge(client=client, signal_engine=signal_engine),
        orchestrator=orchestrator
    )

    started_at = time.time()
    market_events = 0
    user_reports = 0

    def on_market_payload(payload: str) -> None:
        nonlocal market_events
        market_events += 1
        runtime.on_market_payloads([payload])

    def on_user_report(payload: dict[str, object]) -> None:
        nonlocal user_reports
        user_reports += 1
        runtime.on_user_report(payload)

    user_stream: BinanceUserDataStream | None = None
    if not args.skip_user_stream:
        user_stream = BinanceUserDataStream(client, on_user_report)

    logger.info("Starting live session...")

    tasks = [asyncio.create_task(client.stream_depth(args.quote_symbol.upper(), on_market_payload))]
    if user_stream is not None:
        tasks.append(asyncio.create_task(user_stream.start()))

    try:
        await asyncio.sleep(max(1, args.duration_seconds))
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if user_stream is not None:
            await user_stream.stop()
        await client.close_session()

        elapsed = max(0.0, time.time() - started_at)
        open_orders = len(execution_engine._order_tracker.get_open_orders())
        emergency_events = len(runtime.emergency_events)
        logger.info(
            "Session summary: elapsed=%.1fs, market_events=%d, user_reports=%d, open_orders=%d, emergency_events=%d, halted=%s",
            elapsed,
            market_events,
            user_reports,
            open_orders,
            emergency_events,
            runtime.halted,
        )

if __name__ == "__main__":
    asyncio.run(main(parse_args()))
