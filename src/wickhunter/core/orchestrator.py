from dataclasses import dataclass

from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import EngineSubmitResult, MatureEngineAdapter
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.risk.checks import RuntimeRiskState
from wickhunter.strategy.signal_engine import SignalEngine


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    quote_submit: EngineSubmitResult
    hedge_submit: EngineSubmitResult | None


@dataclass(slots=True)
class CoreOrchestrator:
    """Coordinates signal/execution outputs and submits them to a mature backend engine."""

    signal_engine: SignalEngine
    execution_engine: ExecutionEngine
    backend: MatureEngineAdapter

    def on_market_and_fill(
        self,
        *,
        fair_price: float,
        fill: FillEvent,
        risk_state: RuntimeRiskState,
        hedge_reference_price: float,
    ) -> OrchestrationResult:
        plan = self.signal_engine.generate_quote_plan(fair_price=fair_price)
        quote_submit = self.backend.submit_quote_plan(plan)

        exec_result = self.execution_engine.on_b_fill(
            fill=fill,
            state=risk_state,
            reference_price=hedge_reference_price,
        )

        hedge_submit = None
        if exec_result.accepted and exec_result.hedge_order is not None:
            hedge_submit = self.backend.submit_hedge_order(exec_result.hedge_order)

        return OrchestrationResult(quote_submit=quote_submit, hedge_submit=hedge_submit)
