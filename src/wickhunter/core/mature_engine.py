import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from wickhunter.common.events import HedgeOrder
from wickhunter.execution.order_tracker import OrderState, OrderTracker
from wickhunter.strategy.quote_engine import QuotePlan


class MatureEngineKind(str, Enum):
    NAUTILUS_TRADER = "nautilus_trader"
    BINANCE_DIRECT = "binance_direct"


@dataclass(frozen=True, slots=True)
class ExchangeOrderReport:
    intent: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    order_type: str
    time_in_force: str
    accepted: bool
    reason: str
    attempts: int
    exchange_code: int | None = None
    exchange_message: str | None = None
    order_id: int | None = None
    exchange_status: str | None = None
    filled_qty: float = 0.0


@dataclass(frozen=True, slots=True)
class EmergencyStopReport:
    reason: str
    symbol: str
    accepted: bool
    attempts: int
    exchange_code: int | None = None
    exchange_message: str | None = None


@dataclass(frozen=True, slots=True)
class EngineSubmitResult:
    accepted: bool
    backend: MatureEngineKind
    reason: str
    attempts: int = 1
    exchange_code: int | None = None
    exchange_message: str | None = None
    order_id: int | None = None
    client_order_id: str | None = None


class MatureEngineAdapter:
    """Adapter interface for plugging WickHunter into mature trading engines."""

    backend: MatureEngineKind

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:  # pragma: no cover - interface
        raise NotImplementedError

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:  # pragma: no cover - interface
        raise NotImplementedError

    def emergency_stop(self, *, reason: str, symbols: tuple[str, ...]) -> EngineSubmitResult:
        return EngineSubmitResult(accepted=False, backend=self.backend, reason="emergency_not_supported")

    def on_execution_report(self, payload: dict[str, Any]) -> OrderState | None:
        return None


@dataclass(slots=True)
class NautilusTraderAdapter(MatureEngineAdapter):
    """Thin adapter shell; maps WickHunter intents to Nautilus-side commands."""

    backend: MatureEngineKind = MatureEngineKind.NAUTILUS_TRADER
    sent_quote_plans: list[QuotePlan] = field(default_factory=list)
    sent_hedge_orders: list[HedgeOrder] = field(default_factory=list)
    emergency_reasons: list[str] = field(default_factory=list)

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:
        if not plan.armed:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="plan_not_armed")
        self.sent_quote_plans.append(plan)
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:
        if order.qty <= 0 or order.limit_price <= 0:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="invalid_hedge_order")
        self.sent_hedge_orders.append(order)
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")

    def emergency_stop(self, *, reason: str, symbols: tuple[str, ...]) -> EngineSubmitResult:
        self.emergency_reasons.append(reason)
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="emergency_noop")


@dataclass(slots=True)
class BinanceDirectAdapter(MatureEngineAdapter):
    """Direct adapter for Binance testnet/live integration with retry + report capture."""

    backend: MatureEngineKind = MatureEngineKind.BINANCE_DIRECT
    client: Any | None = None
    quote_symbol: str = ""
    quote_order_type: str = "LIMIT"
    quote_time_in_force: str = "GTX"
    hedge_order_type: str = "LIMIT"
    hedge_time_in_force: str = "IOC"
    max_retries: int = 2
    retry_backoff_seconds: float = 0.05
    retryable_error_codes: tuple[int, ...] = (-1001, -1006, -1007, -1008, -1015, -1021)
    order_tracker: OrderTracker = field(default_factory=OrderTracker)
    order_reports: list[ExchangeOrderReport] = field(default_factory=list)
    emergency_reports: list[EmergencyStopReport] = field(default_factory=list)

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:
        if not plan.armed:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="plan_not_armed")
        if self.client is None:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="client_missing")
        if not self.quote_symbol:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="quote_symbol_missing")
        if not plan.levels:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="no_quote_levels")

        level = plan.levels[0]
        client_order_id = self.order_tracker.generate_client_id(prefix="wh_q_")
        self.order_tracker.track_order(
            client_order_id=client_order_id,
            symbol=self.quote_symbol,
            side="BUY",
            qty=level.size,
            price=level.price,
            intent="quote",
        )
        return self._submit_order(
            intent="quote",
            client_order_id=client_order_id,
            symbol=self.quote_symbol,
            side="BUY",
            qty=level.size,
            price=level.price,
            order_type=self.quote_order_type,
            time_in_force=self.quote_time_in_force,
        )

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:
        if order.qty <= 0 or order.limit_price <= 0:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="invalid_hedge_order")
        if self.client is None:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="client_missing")

        client_order_id = self.order_tracker.generate_client_id(prefix="wh_h_")
        self.order_tracker.track_order(
            client_order_id=client_order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=order.limit_price,
            intent="hedge",
        )
        return self._submit_order(
            intent="hedge",
            client_order_id=client_order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=order.limit_price,
            order_type=self.hedge_order_type,
            time_in_force=self.hedge_time_in_force,
        )

    def on_execution_report(self, payload: dict[str, Any]) -> OrderState | None:
        client_order_id = payload.get("clientOrderId") or payload.get("c")
        raw_order_id = payload.get("orderId", payload.get("i"))
        order_id: str | None = None
        if isinstance(raw_order_id, int):
            order_id = str(raw_order_id)
        elif isinstance(raw_order_id, str) and raw_order_id:
            order_id = raw_order_id

        raw_status = payload.get("status", payload.get("X"))
        status = str(raw_status).upper() if raw_status is not None else "NEW"
        raw_filled_qty = payload.get("executedQty", payload.get("z", 0.0))
        try:
            filled_qty = float(raw_filled_qty)
        except (TypeError, ValueError):
            filled_qty = 0.0

        if not client_order_id and not order_id:
            return None

        return self.order_tracker.on_report(
            client_order_id=client_order_id if isinstance(client_order_id, str) else None,
            exchange_order_id=order_id,
            status=self._to_tracker_status(accepted=True, exchange_status=status),
            filled_qty=filled_qty,
        )

    def reconcile_open_orders(self) -> None:
        """Fetch all open orders from exchange and reconcile with local tracker."""
        if self.client is None or not self.quote_symbol:
            return

        try:
            # 1. Fetch from exchange
            raw_open = self._run_coro(self.client.get_open_orders(symbol=self.quote_symbol))
            exchange_open_cids = {o.get("clientOrderId") for o in raw_open if o.get("clientOrderId")}
            
            # 2. Update status for those found in exchange
            for o in raw_open:
                self.on_execution_report(o)

            # 3. For orders we think are open but NOT in exchange_open_cids, fetch individual status
            local_open = self.order_tracker.get_open_orders()
            for order in local_open:
                if order.client_order_id not in exchange_open_cids:
                    try:
                        # Fetch status to see if it was filled/canceled while bot was down
                        detailed = self._run_coro(self.client.get_order_status(
                            symbol=self.quote_symbol,
                            orig_client_order_id=order.client_order_id
                        ))
                        self.on_execution_report(detailed)
                    except Exception:
                        # Order might have been purged or not found
                        pass
        except Exception:
            # Log failure in real implementation
            pass

    def emergency_stop(self, *, reason: str, symbols: tuple[str, ...]) -> EngineSubmitResult:
        if self.client is None:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="client_missing")
        if not symbols:
            return EngineSubmitResult(accepted=True, backend=self.backend, reason="no_symbols")

        for symbol in symbols:
            report = self._cancel_all_orders_for_symbol(symbol=symbol, reason=reason)
            self.emergency_reports.append(report)
            if not report.accepted:
                return EngineSubmitResult(
                    accepted=False,
                    backend=self.backend,
                    reason="emergency_cancel_failed",
                    attempts=report.attempts,
                    exchange_code=report.exchange_code,
                    exchange_message=report.exchange_message,
                )

        return EngineSubmitResult(accepted=True, backend=self.backend, reason="emergency_cancel_ok")

    def _cancel_all_orders_for_symbol(self, *, symbol: str, reason: str) -> EmergencyStopReport:
        max_attempts = max(1, self.max_retries + 1)

        for attempt in range(1, max_attempts + 1):
            try:
                payload = self._run_coro(self.client.cancel_all_open_orders(symbol=symbol))
            except RuntimeError as exc:
                if str(exc) != "running_event_loop":
                    raise
                return EmergencyStopReport(
                    reason=reason,
                    symbol=symbol,
                    accepted=False,
                    attempts=attempt,
                    exchange_message="event_loop_running",
                )
            except Exception as exc:
                report = EmergencyStopReport(
                    reason=reason,
                    symbol=symbol,
                    accepted=False,
                    attempts=attempt,
                    exchange_message=str(exc),
                )
                if attempt >= max_attempts:
                    return report
                self._backoff()
                continue

            code, msg = self._extract_error(payload if isinstance(payload, dict) else {})
            if code is not None and code < 0:
                report = EmergencyStopReport(
                    reason=reason,
                    symbol=symbol,
                    accepted=False,
                    attempts=attempt,
                    exchange_code=code,
                    exchange_message=msg,
                )
                if code in self.retryable_error_codes and attempt < max_attempts:
                    self._backoff()
                    continue
                return report

            return EmergencyStopReport(reason=reason, symbol=symbol, accepted=True, attempts=attempt)

        return EmergencyStopReport(reason=reason, symbol=symbol, accepted=False, attempts=max_attempts)

    def _submit_order(
        self,
        *,
        intent: str,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_type: str,
        time_in_force: str,
    ) -> EngineSubmitResult:
        max_attempts = max(1, self.max_retries + 1)

        for attempt in range(1, max_attempts + 1):
            try:
                payload = self._run_coro(
                    self._build_place_order_coro(
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                        order_type=order_type,
                        time_in_force=time_in_force,
                        client_order_id=client_order_id,
                    )
                )
            except RuntimeError as exc:
                if str(exc) != "running_event_loop":
                    raise
                return self._to_result(
                    ExchangeOrderReport(
                        intent=intent,
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                        order_type=order_type,
                        time_in_force=time_in_force,
                        accepted=False,
                        reason="event_loop_running",
                        attempts=attempt,
                    )
                )
            except Exception as exc:  # pragma: no cover - covered by retry behavior tests
                report = ExchangeOrderReport(
                    intent=intent,
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    price=price,
                    order_type=order_type,
                    time_in_force=time_in_force,
                    accepted=False,
                    reason="client_exception",
                    attempts=attempt,
                    exchange_message=str(exc),
                )
                self.order_reports.append(report)
                if attempt >= max_attempts:
                    self._reconcile_order_tracker(report)
                    return self._to_result(report)
                self._backoff()
                continue

            report = self._build_report_from_payload(
                intent=intent,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                time_in_force=time_in_force,
                attempts=attempt,
                payload=payload,
            )
            self.order_reports.append(report)
            if report.accepted:
                self._reconcile_order_tracker(report)
                return self._to_result(report)

            if report.exchange_code in self.retryable_error_codes and attempt < max_attempts:
                self._backoff()
                continue

            self._reconcile_order_tracker(report)
            return self._to_result(report)

        return EngineSubmitResult(accepted=False, backend=self.backend, reason="unexpected_retry_exit")

    def _build_place_order_coro(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_type: str,
        time_in_force: str,
        client_order_id: str,
    ) -> Any:
        try:
            return self.client.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                time_in_force=time_in_force,
                new_client_order_id=client_order_id,
            )
        except TypeError as exc:
            # Backward compatibility for older client implementations.
            if "new_client_order_id" not in str(exc):
                raise
            return self.client.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                time_in_force=time_in_force,
            )

    def _run_coro(self, coro: Any) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
            if asyncio.iscoroutine(coro):
                coro.close()
            raise RuntimeError("running_event_loop")
        except RuntimeError as exc:
            if str(exc) == "running_event_loop":
                raise
        return asyncio.run(coro)

    def _backoff(self) -> None:
        if self.retry_backoff_seconds > 0:
            time.sleep(self.retry_backoff_seconds)

    def _build_report_from_payload(
        self,
        *,
        intent: str,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_type: str,
        time_in_force: str,
        attempts: int,
        payload: dict[str, Any],
    ) -> ExchangeOrderReport:
        code, msg = self._extract_error(payload)
        order_id = self._extract_order_id(payload)
        exchange_status = payload.get("status")
        filled_qty = self._extract_filled_qty(payload)
        payload_client_order_id = payload.get("clientOrderId")
        resolved_client_order_id = (
            payload_client_order_id if isinstance(payload_client_order_id, str) and payload_client_order_id else client_order_id
        )

        if code is not None and code < 0:
            return ExchangeOrderReport(
                intent=intent,
                client_order_id=resolved_client_order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                time_in_force=time_in_force,
                accepted=False,
                reason=f"exchange_reject:{code}",
                attempts=attempts,
                exchange_code=code,
                exchange_message=msg,
                order_id=order_id,
                exchange_status=exchange_status if isinstance(exchange_status, str) else None,
                filled_qty=filled_qty,
            )

        accepted_status = {"NEW", "PARTIALLY_FILLED", "FILLED"}
        status = payload.get("status")
        if order_id is None and status not in accepted_status:
            return ExchangeOrderReport(
                intent=intent,
                client_order_id=resolved_client_order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                time_in_force=time_in_force,
                accepted=False,
                reason="malformed_exchange_response",
                attempts=attempts,
                exchange_code=code,
                exchange_message=msg,
                order_id=order_id,
                exchange_status=exchange_status if isinstance(exchange_status, str) else None,
                filled_qty=filled_qty,
            )

        return ExchangeOrderReport(
            intent=intent,
            client_order_id=resolved_client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            order_type=order_type,
            time_in_force=time_in_force,
            accepted=True,
            reason="ok",
            attempts=attempts,
            exchange_code=code,
            exchange_message=msg,
            order_id=order_id,
            exchange_status=exchange_status if isinstance(exchange_status, str) else None,
            filled_qty=filled_qty,
        )

    @staticmethod
    def _extract_error(payload: dict[str, Any]) -> tuple[int | None, str | None]:
        raw_code = payload.get("code")
        code: int | None
        if isinstance(raw_code, int):
            code = raw_code
        elif isinstance(raw_code, str) and raw_code.lstrip("-").isdigit():
            code = int(raw_code)
        else:
            code = None

        msg = payload.get("msg")
        return code, msg if isinstance(msg, str) else None

    @staticmethod
    def _extract_order_id(payload: dict[str, Any]) -> int | None:
        raw_order_id = payload.get("orderId")
        if isinstance(raw_order_id, int):
            return raw_order_id
        if isinstance(raw_order_id, str) and raw_order_id.isdigit():
            return int(raw_order_id)
        return None

    @staticmethod
    def _extract_filled_qty(payload: dict[str, Any]) -> float:
        raw_filled_qty = payload.get("executedQty", payload.get("cumQty", payload.get("z", 0.0)))
        try:
            return float(raw_filled_qty)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_tracker_status(*, accepted: bool, exchange_status: str | None) -> str:
        if not accepted:
            return "REJECTED"
        if not exchange_status:
            return "NEW"
        normalized = exchange_status.upper()
        if normalized in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
            return normalized
        if normalized == "PENDING_CANCEL":
            return "CANCELED"
        return "NEW"

    def _reconcile_order_tracker(self, report: ExchangeOrderReport) -> None:
        exchange_order_id = str(report.order_id) if report.order_id is not None else None
        self.order_tracker.on_report(
            client_order_id=report.client_order_id,
            exchange_order_id=exchange_order_id,
            status=self._to_tracker_status(accepted=report.accepted, exchange_status=report.exchange_status),
            filled_qty=report.filled_qty,
        )

    def _to_result(self, report: ExchangeOrderReport) -> EngineSubmitResult:
        return EngineSubmitResult(
            accepted=report.accepted,
            backend=self.backend,
            reason=report.reason,
            attempts=report.attempts,
            exchange_code=report.exchange_code,
            exchange_message=report.exchange_message,
            order_id=report.order_id,
            client_order_id=report.client_order_id,
        )
