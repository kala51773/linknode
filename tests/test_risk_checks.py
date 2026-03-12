import unittest

from wickhunter.common.config import RiskLimits
from wickhunter.risk.checks import (
    AccountRiskSnapshot,
    RiskChecker,
    build_account_snapshot_from_binance,
)


class TestRiskAccountChecks(unittest.TestCase):
    def test_build_account_snapshot_prefers_usdt(self) -> None:
        payload = {
            "B": [
                {"a": "BTC", "wb": "1.0", "cw": "0.2"},
                {"a": "USDT", "wb": "100.0", "cw": "20.0", "bc": "-1.0"},
            ]
        }
        snapshot = build_account_snapshot_from_binance(payload)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.asset, "USDT")
        self.assertAlmostEqual(snapshot.available_balance_ratio or 0.0, 0.2)

    def test_build_account_snapshot_returns_none_when_missing_balances(self) -> None:
        self.assertIsNone(build_account_snapshot_from_binance({"x": 1}))

    def test_can_accept_account_snapshot_rejects_low_available_ratio(self) -> None:
        checker = RiskChecker(RiskLimits(min_available_balance_ratio=0.1, min_wallet_balance_usdt=10.0))
        snapshot = AccountRiskSnapshot(
            ts_ms=1,
            asset="USDT",
            wallet_balance=100.0,
            cross_wallet_balance=2.0,
            available_balance_ratio=0.02,
        )
        allowed, reason = checker.can_accept_account_snapshot(snapshot)

        self.assertFalse(allowed)
        self.assertEqual(reason, "available_balance_ratio")


if __name__ == "__main__":
    unittest.main()
