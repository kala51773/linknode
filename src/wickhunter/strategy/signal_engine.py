from dataclasses import dataclass

from wickhunter.exchange.models import NormalizedDepthEvent
from wickhunter.marketdata.calculators import compute_microstructure_metrics
from wickhunter.marketdata.orderbook import DepthUpdate
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.strategy.quote_engine import QuoteEngine, QuotePlan
from wickhunter.strategy.alpha import ResidualModel, FairValue


@dataclass(slots=True)
class SignalEngine:
    """Small end-to-end signal path: sync book -> compute metrics -> build quote plan."""

    quote_engine: QuoteEngine
    baseline_depth_5bp: float
    synchronizer: BookSynchronizer
    residual_model: ResidualModel | None = None
    last_fair_value: FairValue | None = None

    def on_depth_update(self, update: DepthUpdate) -> None:
        self.synchronizer.on_depth_update(update)

    def on_normalized_depth_event(self, event: NormalizedDepthEvent) -> None:
        self.on_depth_update(
            DepthUpdate(
                first_update_id=event.first_update_id,
                final_update_id=event.final_update_id,
                prev_final_update_id=event.prev_final_update_id,
                bids=event.bids,
                asks=event.asks,
            )
        )

    def on_snapshot(
        self,
        *,
        last_update_id: int,
        bids: tuple[tuple[float, float], ...],
        asks: tuple[tuple[float, float], ...],
    ) -> None:
        self.synchronizer.apply_snapshot(last_update_id=last_update_id, bids=bids, asks=asks)

    def generate_quote_plan(self, fair_price: float, p_A: float = 1.0, p_sector: float = 1.0) -> QuotePlan:
        if not self.synchronizer.is_synced:
            return QuotePlan(armed=False, levels=tuple(), reason="not_synced")

        if self.residual_model and self.synchronizer.book.mid_price:
            self.last_fair_value = self.residual_model.compute_fair_value(
                p_B_local=self.synchronizer.book.mid_price,
                p_A=p_A,
                p_sector=p_sector,
                cross_venue_fair=fair_price
            )
            fair_price = self.last_fair_value.fair_price

        metrics = compute_microstructure_metrics(self.synchronizer.book)
        armed, reason = self.quote_engine.should_arm(metrics, baseline_depth_5bp=self.baseline_depth_5bp)
        return self.quote_engine.build_plan(fair_price=fair_price, armed=armed, reason=reason)
