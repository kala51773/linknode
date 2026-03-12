import unittest

import numpy as np
import pandas as pd

from wickhunter.strategy.discover import DiscoverConfig, DiscoverEngine
from wickhunter.strategy.pair_selector import PairSelector
from wickhunter.strategy.stats import CointegrationStatsModel
from wickhunter.strategy.universe import UniverseManager


class TestDiscoverEngine(unittest.TestCase):
    def test_auto_discovery_selects_low_liquidity_high_corr_b(self) -> None:
        idx = pd.RangeIndex(start=0, stop=1200, step=1)
        base = np.exp(np.linspace(10.0, 10.4, len(idx)) + 0.004 * np.sin(np.arange(len(idx)) / 20))
        b_good = base * np.exp(0.0015 * np.sin(np.arange(len(idx)) / 6))
        b_too_liquid = base * np.exp(0.0012 * np.sin(np.arange(len(idx)) / 5))
        b_low_corr = np.exp(np.linspace(10.5, 10.0, len(idx)) + 0.1 * np.sin(np.arange(len(idx)) / 4))

        price_history = {
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
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "quoteVolume": 2_500_000_000},
            {"symbol": "ALT1USDT", "baseAsset": "ALT1", "quoteAsset": "USDT", "quoteVolume": 130_000_000},
            {"symbol": "ALT2USDT", "baseAsset": "ALT2", "quoteAsset": "USDT", "quoteVolume": 1_200_000_000},
            {"symbol": "ALT3USDT", "baseAsset": "ALT3", "quoteAsset": "USDT", "quoteVolume": 100_000_000},
        ]

        engine = DiscoverEngine(
            universe=UniverseManager(),
            selector=PairSelector(),
            stats_model=CointegrationStatsModel(),
        )
        pairs = engine.run_auto_discovery_multi_tf(
            raw_markets=raw_markets,
            price_history_by_tf=price_history,
            config=DiscoverConfig(
                anchor_symbols=("BTCUSDT",),
                min_daily_volume_usd=50_000_000,
                max_daily_volume_usd=400_000_000,
                min_b_to_a_volume_ratio=0.02,
                max_b_to_a_volume_ratio=0.20,
                target_b_to_a_volume_ratio=0.08,
                min_history_points=300,
                min_history_points_by_tf={"1d": 300, "4h": 300},
                timeframes=("1d", "4h"),
                timeframe_weights={"1d": 0.6, "4h": 0.4},
                top_k=3,
            ),
        )

        self.assertGreaterEqual(len(pairs), 1)
        self.assertEqual(pairs[0].pair_a, "BTCUSDT")
        self.assertEqual(pairs[0].pair_b, "ALT1USDT")
        self.assertGreater(pairs[0].components.get("corr_30d", 0.0), 0.7)
        self.assertLess(pairs[0].components.get("volume_ratio_b_to_a", 1.0), 0.2)

    def test_liquidity_penalty_prefers_target_ratio(self) -> None:
        selector = PairSelector()
        near_target = selector.liquidity_penalty_by_ratio(
            b_to_a_volume_ratio=0.1, target_ratio=0.1, min_ratio=0.02, max_ratio=0.35
        )
        edge = selector.liquidity_penalty_by_ratio(
            b_to_a_volume_ratio=0.34, target_ratio=0.1, min_ratio=0.02, max_ratio=0.35
        )
        out_of_range = selector.liquidity_penalty_by_ratio(
            b_to_a_volume_ratio=0.6, target_ratio=0.1, min_ratio=0.02, max_ratio=0.35
        )

        self.assertLess(near_target, edge)
        self.assertEqual(out_of_range, 1.0)


if __name__ == "__main__":
    unittest.main()
