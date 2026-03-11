import unittest
from typing import Any

from wickhunter.common.events import HedgeOrder
from wickhunter.core.mature_engine import BinanceDirectAdapter, MatureEngineKind, NautilusTraderAdapter
from wickhunter.strategy.quote_engine import QuoteLevel, QuotePlan


class TestMatureEngineAdapter(unittest.TestCase):
    def test_submit_armed_plan_to_nautilus_adapter(self) -> None:
        adapter = NautilusTraderAdapter()
        plan = QuotePlan(armed=True, levels=(QuoteLevel(price=99.4, size=100),), reason="ok")

        result = adapter.submit_quote_plan(plan)

        self.assertTrue(result.accepted)
        self.assertEqual(result.backend, MatureEngineKind.NAUTILUS_TRADER)
        self.assertEqual(len(adapter.sent_quote_plans), 1)

    def test_reject_unarmed_plan(self) -> None:
        adapter = NautilusTraderAdapter()
        result = adapter.submit_quote_plan(QuotePlan(armed=False, levels=tuple(), reason="not_synced"))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "plan_not_armed")

    def test_submit_hedge_order(self) -> None:
        adapter = NautilusTraderAdapter()
        order = HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.01, limit_price=50_000)

        result = adapter.submit_hedge_order(order)

        self.assertTrue(result.accepted)
        self.assertEqual(len(adapter.sent_hedge_orders), 1)

    def test_nautilus_emergency_stop_noop(self) -> None:
        adapter = NautilusTraderAdapter()

        result = adapter.emergency_stop(reason="marketdata_latency", symbols=("BTCUSDT",))

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "emergency_noop")
        self.assertEqual(adapter.emergency_reasons, ["marketdata_latency"])


class FakeBinanceClient:
    def __init__(self, responses: list[Any], cancel_responses: list[Any] | None = None) -> None:
        self.responses = list(responses)
        self.cancel_responses = list(cancel_responses or [])
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[str] = []

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = 0.0,
        order_type: str = "LIMIT",
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "order_type": order_type,
                "time_in_force": time_in_force,
            }
        )

        if not self.responses:
            raise RuntimeError("no_fake_response")

        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def cancel_all_open_orders(self, symbol: str) -> Any:
        self.cancel_calls.append(symbol)
        if not self.cancel_responses:
            return {"status": "ok"}
        nxt = self.cancel_responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class TestBinanceDirectAdapter(unittest.TestCase):
    def test_submit_hedge_order_success(self) -> None:
        client = FakeBinanceClient([{"orderId": 101, "status": "NEW"}])
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertTrue(result.accepted)
        self.assertEqual(result.backend, MatureEngineKind.BINANCE_DIRECT)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.order_id, 101)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(adapter.order_reports[-1].intent, "hedge")

    def test_retry_on_retryable_code_then_success(self) -> None:
        client = FakeBinanceClient(
            [
                {"code": -1007, "msg": "Timeout waiting for response from backend server."},
                {"orderId": 202, "status": "NEW"},
            ]
        )
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertTrue(result.accepted)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(adapter.order_reports[0].exchange_code, -1007)
        self.assertEqual(adapter.order_reports[1].order_id, 202)

    def test_reject_non_retryable_exchange_error(self) -> None:
        client = FakeBinanceClient([{"code": -2019, "msg": "Margin is insufficient."}])
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "exchange_reject:-2019")
        self.assertEqual(result.exchange_code, -2019)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(client.calls), 1)

    def test_submit_quote_plan_uses_first_level(self) -> None:
        client = FakeBinanceClient([{"orderId": 303, "status": "NEW"}])
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ALTUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        plan = QuotePlan(
            armed=True,
            levels=(QuoteLevel(price=99.1, size=10.0), QuoteLevel(price=98.0, size=20.0)),
            reason="ok",
        )

        result = adapter.submit_quote_plan(plan)

        self.assertTrue(result.accepted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["symbol"], "ALTUSDT")
        self.assertEqual(client.calls[0]["side"], "BUY")
        self.assertEqual(client.calls[0]["price"], 99.1)
        self.assertEqual(client.calls[0]["qty"], 10.0)

    def test_submit_quote_plan_missing_symbol_rejected(self) -> None:
        client = FakeBinanceClient([])
        adapter = BinanceDirectAdapter(client=client)
        plan = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1, size=10.0),), reason="ok")

        result = adapter.submit_quote_plan(plan)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "quote_symbol_missing")

    def test_emergency_stop_cancel_all_symbols(self) -> None:
        client = FakeBinanceClient([], cancel_responses=[{"status": "ok"}, {"status": "ok"}])
        adapter = BinanceDirectAdapter(client=client, max_retries=1, retry_backoff_seconds=0.0)

        result = adapter.emergency_stop(reason="marketdata_latency", symbols=("BTCUSDT", "ETHUSDT"))

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "emergency_cancel_ok")
        self.assertEqual(client.cancel_calls, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(len(adapter.emergency_reports), 2)
        self.assertTrue(all(r.accepted for r in adapter.emergency_reports))

    def test_emergency_stop_retry_and_fail(self) -> None:
        client = FakeBinanceClient(
            [],
            cancel_responses=[
                {"code": -1007, "msg": "Timeout"},
                {"code": -2019, "msg": "Margin is insufficient."},
            ],
        )
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.emergency_stop(reason="exchange_restricted", symbols=("BTCUSDT",))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "emergency_cancel_failed")
        self.assertEqual(result.exchange_code, -2019)
        self.assertEqual(client.cancel_calls, ["BTCUSDT", "BTCUSDT"])
        self.assertEqual(len(adapter.emergency_reports), 1)
        self.assertFalse(adapter.emergency_reports[0].accepted)


if __name__ == "__main__":
    unittest.main()
