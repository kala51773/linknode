import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import NautilusTraderAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState
from wickhunter.runtime import WickHunterRuntime
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine
from wickhunter.simulation.hedge_latency import HedgeLatencyModel
from wickhunter.analytics.report import EventPnL, build_event_report, EventReport


@dataclass(slots=True)
class L2Simulator:
    """A minimal simulator that plays back JSONL events, triggers strategy, and matches fake fills against L2 states."""
    
    runtime: WickHunterRuntime
    latency_model: HedgeLatencyModel = field(default_factory=HedgeLatencyModel)
    
    _pnls: list[EventPnL] = field(default_factory=list)
    _hedge_results: list = field(default_factory=list)
    _risk_state: RuntimeRiskState = field(default_factory=RuntimeRiskState)

    def run(self, file_path: Path) -> EventReport:
        with file_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                
                payload = json.loads(raw)
                event_type = payload.get("event")
                
                if event_type == "snapshot":
                    self.runtime.on_snapshot(
                        last_update_id=int(payload["last_update_id"]),
                        bids=tuple((float(p), float(q)) for p, q in payload["bids"]),
                        asks=tuple((float(p), float(q)) for p, q in payload["asks"]),
                    )
                elif event_type == "depthUpdate":
                    # Send payload str directly to runtime's bridge using the original binance format string in 'raw_payload'
                    raw_binance = payload["raw_payload"]
                    self.runtime.on_market_payloads([raw_binance])
                
                elif event_type == "trade":
                    # A market trade event (e.g. someone else sold to the orderbook)
                    trade_px = float(payload["price"])
                    trade_qty = float(payload["qty"])
                    trade_side = payload["side"]  # "SELL" means taker sold
                    
                    # Generate a signal to get the current quote plan (we need fair price for it, we'll proxy it using mid_price)
                    # For realistic simulation, we use the mid price as the fair price proxy
                    book = self.runtime.bridge.signal_engine.synchronizer.book
                    if not book.mid_price:
                        continue
                    
                    fair_price = book.mid_price
                    # Get quote plan 
                    plan = self.runtime.bridge.signal_engine.generate_quote_plan(fair_price=fair_price)
                    
                    if plan.armed and trade_side == "SELL":
                        # If taker sold, they match against our bids
                        for level in plan.levels:
                            if trade_px <= level.price:
                                # We got filled!
                                fill_qty = min(level.size, trade_qty)
                                fill = FillEvent(symbol=payload["symbol"], qty=fill_qty, price=level.price, side="BUY")
                                
                                # Process the fill in the runtime and generate hedge
                                step_res = self.runtime.step(
                                    fair_price=fair_price,
                                    fill=fill,
                                    risk_state=self._risk_state,
                                    hedge_reference_price=fair_price,  # use same fair price for hedging reference
                                    marketdata_latency_ms=10,
                                    consecutive_hedge_failures=0,
                                    exchange_restricted=False,
                                )
                                
                                if step_res.hedge_submitted:
                                    # We simulate the hedge execution
                                    hedge_result = self.latency_model.simulate(hedge_notional=fill_qty * level.price)
                                    self._hedge_results.append(hedge_result)
                                    
                                    # Mock PnL (gross pnl = difference between B leg fill and A leg hedge limits)
                                    # Assuming beta_exec=1.0 and identical fair price so the spread minus slippage is our profit
                                    # slippage is represented as BPS of notional
                                    notional = fill_qty * level.price
                                    # For B limit passive fill maker fee is usually 0.00% or slightly negative, we use 0
                                    # For A taker fill we use 0.04% fee
                                    fees = notional * 0.0004
                                    # PnL captured = (fair_price - bid_price) - slippage_loss
                                    gross_pnl = (fair_price - level.price) * fill_qty - (hedge_result.expected_slippage_bps / 10000) * notional
                                    
                                    self._pnls.append(EventPnL(gross_pnl=gross_pnl, fees=fees, funding=0.0))
                                
                                # Consume trade qty
                                trade_qty -= fill_qty
                                if trade_qty <= 0:
                                    break

        return build_event_report(self._pnls, self._hedge_results)


def create_default_l2_simulator() -> L2Simulator:
    signal_engine = SignalEngine(
        quote_engine=QuoteEngine(max_name_risk=1_000, theta1=0.001), # tighter theta for test
        baseline_depth_5bp=20.0, # low baseline so a 1.0 qty doesn't disqualify us
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
                hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0, aggressiveness_bps=1.0),
            ),
            backend=NautilusTraderAdapter(),
        ),
    )
    return L2Simulator(runtime=runtime)
