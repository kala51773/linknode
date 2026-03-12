import argparse
import asyncio
import logging
import time

from wickhunter.common.config import ExchangeConfig, RiskLimits
from wickhunter.common.health_export import HealthExporter
from wickhunter.core.mature_engine import BinanceDirectAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.binance_live import BinanceUserDataStream
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.risk.checks import RiskChecker
from wickhunter.runtime import WickHunterRuntime
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine

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
    parser.add_argument("--health-output", default="", help="Optional path for health export file.")
    parser.add_argument(
        "--health-format",
        choices=("jsonl", "prometheus"),
        default="jsonl",
        help="Health output format.",
    )
    parser.add_argument(
        "--health-interval-seconds",
        type=float,
        default=5.0,
        help="Health export interval in seconds.",
    )
    parser.add_argument(
        "--startup-reconcile-attempts",
        type=int,
        default=3,
        help="Retry attempts for startup reconcile when exchange query fails.",
    )
    parser.add_argument(
        "--startup-reconcile-backoff-seconds",
        type=float,
        default=1.0,
        help="Backoff seconds between startup reconcile retries.",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    ex_config = ExchangeConfig.from_env()
    if not args.skip_user_stream and (not ex_config.api_key or not ex_config.api_secret):
        raise RuntimeError("Missing BINANCE_API_KEY/BINANCE_API_SECRET for live run.")

    client = BinanceFuturesClient(
        depth_parser=BinanceFuturesDepthParser(),
        api_key=ex_config.api_key,
        api_secret=ex_config.api_secret,
        rest_url=ex_config.rest_url,
        ws_url=ex_config.ws_url,
    )

    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1000),
        baseline_depth_5bp=100.0,
        synchronizer=BookSynchronizer(),
    )

    execution_engine = ExecutionEngine(
        risk_checker=RiskChecker(RiskLimits()),
        hedge_manager=HedgeManager(hedge_symbol=args.hedge_symbol.upper(), beta_exec=1.0),
    )
    execution_engine.recover_state()

    backend = BinanceDirectAdapter(
        client=client,
        quote_symbol=args.quote_symbol.upper(),
        order_tracker=execution_engine._order_tracker,
    )
    if not args.skip_user_stream:
        reconcile = None
        attempts = max(1, int(args.startup_reconcile_attempts))
        backoff_seconds = max(0.0, float(args.startup_reconcile_backoff_seconds))
        for idx in range(1, attempts + 1):
            reconcile = await asyncio.to_thread(backend.reconcile_open_orders_strict)
            # Reconcile runs in a worker thread; reset aiohttp session so future REST calls
            # are bound to the main event loop.
            await client.close_session()
            if reconcile.success:
                break
            if idx < attempts and reconcile.reason == "reconcile_exchange_query_failed":
                logger.warning(
                    "Startup reconcile attempt %d/%d failed: %s (%s). Retrying...",
                    idx,
                    attempts,
                    reconcile.reason,
                    reconcile.error_detail or "no_detail",
                )
                await asyncio.sleep(backoff_seconds)
                continue
            break

        assert reconcile is not None
        if not reconcile.success:
            raise RuntimeError(
                "startup_reconcile_failed:"
                f"{reconcile.reason}:unresolved={reconcile.unresolved_local}:"
                f"status_query_failures={reconcile.status_query_failures}:"
                f"detail={reconcile.error_detail or 'none'}"
            )
        logger.info(
            "Startup reconcile OK: exchange_open=%d local_before=%d local_after=%d resolved=%d assumed_closed=%d",
            reconcile.exchange_open_orders,
            reconcile.local_open_before,
            reconcile.local_open_after,
            reconcile.resolved_via_status,
            reconcile.assumed_closed,
        )

    orchestrator = CoreOrchestrator(
        signal_engine=signal_engine,
        execution_engine=execution_engine,
        backend=backend,
    )

    runtime = WickHunterRuntime(
        bridge=BinanceSignalBridge(client=client, signal_engine=signal_engine),
        orchestrator=orchestrator,
    )
    health_exporter = HealthExporter(args.health_output, args.health_format) if args.health_output else None

    started_at = time.time()
    market_events = 0
    user_reports = 0
    account_updates = 0
    listen_key_expired_events = 0

    def on_market_payload(payload: str) -> None:
        nonlocal market_events
        market_events += 1
        runtime.on_market_payloads([payload])

    def on_user_report(payload: dict[str, object]) -> None:
        nonlocal user_reports
        user_reports += 1
        runtime.on_user_report(payload)

    def on_account_update(payload: dict[str, object]) -> None:
        nonlocal account_updates
        account_updates += 1
        runtime.on_account_update(payload)
        logger.debug("Account update received: keys=%s", list(payload.keys()))

    def on_stream_event(event_type: str, payload: dict[str, object]) -> None:
        nonlocal listen_key_expired_events
        if event_type == "listen_key_expired":
            listen_key_expired_events += 1
            logger.warning("User stream listen key expired. Keys=%s", list(payload.keys()))

    user_stream: BinanceUserDataStream | None = None
    if not args.skip_user_stream:
        user_stream = BinanceUserDataStream(
            client=client,
            report_callback=on_user_report,
            account_callback=on_account_update,
            stream_event_callback=on_stream_event,
        )

    logger.info("Starting live session...")

    tasks = [asyncio.create_task(client.stream_depth(args.quote_symbol.upper(), on_market_payload))]
    if user_stream is not None:
        tasks.append(asyncio.create_task(user_stream.start()))

    health_stop_event = asyncio.Event()

    def build_health_snapshot() -> dict[str, object]:
        elapsed = max(0.0, time.time() - started_at)
        snapshot: dict[str, object] = {
            "ts_ms": int(time.time() * 1000),
            "elapsed_seconds": round(elapsed, 3),
            "market_events": market_events,
            "user_reports": user_reports,
            "account_updates": account_updates,
            "listen_key_expired_events": listen_key_expired_events,
            "open_orders": len(execution_engine._order_tracker.get_open_orders()),
            "emergency_events": len(runtime.emergency_events),
            "runtime_halted": runtime.halted,
            "account_risk_reject_count": runtime.account_risk_reject_count,
        }
        if user_stream is not None:
            snapshot["user_stream_decode_errors"] = user_stream.decode_error_count
            snapshot["listen_key_refresh_count"] = user_stream.listen_key_refresh_count
            snapshot["listen_key_create_failures"] = user_stream.listen_key_create_failures
        if runtime.last_account_snapshot is not None:
            account = runtime.last_account_snapshot
            snapshot["account_wallet_balance"] = account.wallet_balance
            snapshot["account_cross_wallet_balance"] = account.cross_wallet_balance or 0.0
            snapshot["account_available_balance_ratio"] = account.available_balance_ratio or 0.0
        return snapshot

    async def health_loop() -> None:
        if health_exporter is None:
            return
        interval = max(0.5, float(args.health_interval_seconds))
        while not health_stop_event.is_set():
            health_exporter.write_snapshot(build_health_snapshot())
            try:
                await asyncio.wait_for(health_stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
        health_exporter.write_snapshot(build_health_snapshot())

    health_task = asyncio.create_task(health_loop()) if health_exporter is not None else None

    try:
        deadline = time.time() + max(1, args.duration_seconds)
        while time.time() < deadline and not runtime.halted:
            await asyncio.sleep(0.5)
        if runtime.halted:
            logger.error("Runtime halted by risk or emergency condition. Ending live session early.")
    finally:
        health_stop_event.set()
        if health_task is not None:
            await health_task
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
            "Session summary: elapsed=%.1fs, market_events=%d, user_reports=%d, account_updates=%d, "
            "listen_key_expired=%d, open_orders=%d, emergency_events=%d, halted=%s",
            elapsed,
            market_events,
            user_reports,
            account_updates,
            listen_key_expired_events,
            open_orders,
            emergency_events,
            runtime.halted,
        )


def cli_main() -> None:
    asyncio.run(main(parse_args()))

if __name__ == "__main__":
    cli_main()
