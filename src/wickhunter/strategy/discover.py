import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from wickhunter.strategy.pair_selector import PairScore, PairSelector
from wickhunter.strategy.stats import CointegrationStatsModel
from wickhunter.strategy.universe import UniverseManager

logger = logging.getLogger("wickhunter.discover")


@dataclass(slots=True)
class DiscoverConfig:
    anchor_symbols: tuple[str, ...] = ("BTCUSDT",)
    quote_asset: str = "USDT"
    min_daily_volume_usd: float = 3_000_000.0
    max_daily_volume_usd: float = 300_000_000.0
    min_b_to_a_volume_ratio: float = 0.02
    max_b_to_a_volume_ratio: float = 0.35
    target_b_to_a_volume_ratio: float = 0.10
    min_corr: float = 0.70
    min_r2: float = 0.35
    max_beta_instability: float = 0.60
    min_half_life_seconds: float = 10.0
    max_half_life_seconds: float = 600.0
    min_history_points: int = 300
    min_history_points_by_tf: dict[str, int] | None = None
    timeframes: tuple[str, ...] = ("1d", "4h")
    timeframe_weights: dict[str, float] | None = None
    top_k: int = 5
    excluded_symbols: tuple[str, ...] = ()


class DiscoverEngine:
    """DISCOVER state component for choosing B symbols against liquid anchor A."""

    def __init__(
        self,
        universe: UniverseManager,
        selector: PairSelector,
        stats_model: CointegrationStatsModel | None = None,
    ) -> None:
        self.universe = universe
        self.selector = selector
        self.stats_model = stats_model or CointegrationStatsModel()
        self.top_pairs: list[PairScore] = []

    def run_discovery_cycle(
        self,
        raw_markets: list[dict[str, Any]],
        stats_matrix: dict[str, dict[str, float]],
    ) -> list[PairScore]:
        """
        Legacy 30m cycle using pre-computed stats matrix.
        stats_matrix maps "B_symbol|A_symbol" to metrics dict.
        """
        logger.info("Starting DISCOVER cycle.")
        self.universe.update_from_exchange(raw_markets)
        candidates = self.universe.filter_by_min_volume(1_000_000)

        scores: list[PairScore] = []
        a_candidates = [c for c in candidates if c.symbol in ("BTCUSDT", "ETHUSDT")]
        b_candidates = [c for c in candidates if c.symbol not in ("BTCUSDT", "ETHUSDT")]

        for a_meta in a_candidates:
            for b_meta in b_candidates:
                pair_key = f"{b_meta.symbol}|{a_meta.symbol}"
                stats = stats_matrix.get(pair_key, {})
                if not stats:
                    continue
                score = self.selector.score_pair(b_meta, a_meta, stats)
                if score.score > 0:
                    scores.append(score)

        scores.sort(key=lambda x: x.score, reverse=True)
        self.top_pairs = scores[:5]
        logger.info("DISCOVER cycle complete. Found %d candidate pairs.", len(self.top_pairs))
        return self.top_pairs

    def run_auto_discovery(
        self,
        *,
        raw_markets: list[dict[str, Any]],
        price_history: dict[str, pd.Series],
        config: DiscoverConfig | None = None,
    ) -> list[PairScore]:
        cfg = config or DiscoverConfig()
        self.universe.update_from_exchange(raw_markets)

        anchor_set = {s.upper() for s in cfg.anchor_symbols}
        anchors = self.universe.filter_for_discovery(
            quote_asset=cfg.quote_asset,
            min_volume_usd=cfg.min_daily_volume_usd,
            allowed_symbols=anchor_set,
        )
        if not anchors:
            self.top_pairs = []
            return self.top_pairs

        excluded = set(s.upper() for s in cfg.excluded_symbols)
        excluded.update(anchor_set)
        b_candidates = self.universe.filter_for_discovery(
            quote_asset=cfg.quote_asset,
            min_volume_usd=cfg.min_daily_volume_usd,
            max_volume_usd=cfg.max_daily_volume_usd,
            excluded_symbols=excluded,
        )

        scores: list[PairScore] = []
        for a_meta in anchors:
            a_prices = price_history.get(a_meta.symbol)
            if a_prices is None or len(a_prices) < cfg.min_history_points:
                continue

            for b_meta in b_candidates:
                b_prices = price_history.get(b_meta.symbol)
                if b_prices is None or len(b_prices) < cfg.min_history_points:
                    continue
                if a_meta.volume_24h_usd <= 0:
                    continue

                ratio = b_meta.volume_24h_usd / a_meta.volume_24h_usd
                if ratio < cfg.min_b_to_a_volume_ratio or ratio > cfg.max_b_to_a_volume_ratio:
                    continue

                stats = self.stats_model.calculate_stats(prices_a=a_prices, prices_b=b_prices)
                liq_penalty = self.selector.liquidity_penalty_by_ratio(
                    b_to_a_volume_ratio=ratio,
                    target_ratio=cfg.target_b_to_a_volume_ratio,
                    min_ratio=cfg.min_b_to_a_volume_ratio,
                    max_ratio=cfg.max_b_to_a_volume_ratio,
                )
                score_stats = {
                    "corr_30d": stats.corr_30d,
                    "r2_6h": stats.r2_6h,
                    "beta_instability": stats.beta_instability,
                    "half_life_seconds": stats.half_life_seconds,
                    "liquidity_penalty": liq_penalty,
                    "volume_ratio_b_to_a": ratio,
                    "mean_spread": stats.mean_spread,
                    "beta": stats.beta,
                }
                score = self.selector.score_pair(
                    b_meta=b_meta,
                    a_meta=a_meta,
                    stats=score_stats,
                    min_corr=cfg.min_corr,
                    min_r2=cfg.min_r2,
                    max_beta_instability=cfg.max_beta_instability,
                    min_half_life_seconds=cfg.min_half_life_seconds,
                    max_half_life_seconds=cfg.max_half_life_seconds,
                )
                if score.score > 0:
                    scores.append(score)

        scores.sort(key=lambda item: item.score, reverse=True)
        self.top_pairs = scores[: max(1, cfg.top_k)]
        return self.top_pairs

    def run_auto_discovery_multi_tf(
        self,
        *,
        raw_markets: list[dict[str, Any]],
        price_history_by_tf: dict[str, dict[str, pd.Series]],
        config: DiscoverConfig | None = None,
    ) -> list[PairScore]:
        cfg = config or DiscoverConfig()
        self.universe.update_from_exchange(raw_markets)

        anchor_set = {s.upper() for s in cfg.anchor_symbols}
        anchors = self.universe.filter_for_discovery(
            quote_asset=cfg.quote_asset,
            min_volume_usd=cfg.min_daily_volume_usd,
            allowed_symbols=anchor_set,
        )
        if not anchors:
            self.top_pairs = []
            return self.top_pairs

        excluded = set(s.upper() for s in cfg.excluded_symbols)
        excluded.update(anchor_set)
        b_candidates = self.universe.filter_for_discovery(
            quote_asset=cfg.quote_asset,
            min_volume_usd=cfg.min_daily_volume_usd,
            max_volume_usd=cfg.max_daily_volume_usd,
            excluded_symbols=excluded,
        )

        weights = cfg.timeframe_weights or {tf: 1.0 for tf in cfg.timeframes}
        total_weight = sum(weights.get(tf, 0.0) for tf in cfg.timeframes)
        if total_weight <= 0:
            total_weight = 1.0

        min_points_by_tf = cfg.min_history_points_by_tf or {}
        scores: list[PairScore] = []
        for a_meta in anchors:
            a_tf = price_history_by_tf.get(a_meta.symbol, {})
            if not a_tf:
                continue

            for b_meta in b_candidates:
                b_tf = price_history_by_tf.get(b_meta.symbol, {})
                if not b_tf:
                    continue
                if a_meta.volume_24h_usd <= 0:
                    continue

                ratio = b_meta.volume_24h_usd / a_meta.volume_24h_usd
                if ratio < cfg.min_b_to_a_volume_ratio or ratio > cfg.max_b_to_a_volume_ratio:
                    continue

                stats_by_tf: dict[str, dict[str, float]] = {}
                for tf in cfg.timeframes:
                    a_series = a_tf.get(tf)
                    b_series = b_tf.get(tf)
                    if a_series is None or b_series is None:
                        continue
                    min_points = min_points_by_tf.get(tf, cfg.min_history_points)
                    if len(a_series) < min_points or len(b_series) < min_points:
                        continue
                    stats = self.stats_model.calculate_stats(prices_a=a_series, prices_b=b_series)
                    stats_by_tf[tf] = {
                        "corr": stats.corr_30d,
                        "r2": stats.r2_6h,
                        "beta": stats.beta,
                        "beta_instability": stats.beta_instability,
                        "half_life_seconds": stats.half_life_seconds,
                        "mean_spread": stats.mean_spread,
                    }

                if not stats_by_tf:
                    continue

                def wavg(key: str) -> float:
                    total = 0.0
                    used = 0.0
                    for tf, stats in stats_by_tf.items():
                        w = weights.get(tf, 0.0)
                        val = stats.get(key)
                        if val is None:
                            continue
                        total += w * float(val)
                        used += w
                    return total / used if used > 0 else 0.0

                corr = wavg("corr")
                r2 = wavg("r2")
                beta = wavg("beta")
                beta_instability = wavg("beta_instability")
                half_life = wavg("half_life_seconds")
                mean_spread = wavg("mean_spread")

                liq_penalty = self.selector.liquidity_penalty_by_ratio(
                    b_to_a_volume_ratio=ratio,
                    target_ratio=cfg.target_b_to_a_volume_ratio,
                    min_ratio=cfg.min_b_to_a_volume_ratio,
                    max_ratio=cfg.max_b_to_a_volume_ratio,
                )

                score_stats = {
                    "corr_30d": corr,
                    "r2_6h": r2,
                    "beta_instability": beta_instability,
                    "half_life_seconds": half_life,
                    "liquidity_penalty": liq_penalty,
                    "volume_ratio_b_to_a": ratio,
                    "mean_spread": mean_spread,
                    "beta": beta,
                }
                for tf, stats in stats_by_tf.items():
                    score_stats[f"corr_{tf}"] = stats["corr"]
                    score_stats[f"r2_{tf}"] = stats["r2"]
                    score_stats[f"beta_{tf}"] = stats["beta"]
                    score_stats[f"beta_instability_{tf}"] = stats["beta_instability"]
                    score_stats[f"half_life_seconds_{tf}"] = stats["half_life_seconds"]

                score = self.selector.score_pair(
                    b_meta=b_meta,
                    a_meta=a_meta,
                    stats=score_stats,
                    min_corr=cfg.min_corr,
                    min_r2=cfg.min_r2,
                    max_beta_instability=cfg.max_beta_instability,
                    min_half_life_seconds=cfg.min_half_life_seconds,
                    max_half_life_seconds=cfg.max_half_life_seconds,
                )
                if score.score > 0:
                    scores.append(score)

        scores.sort(key=lambda item: item.score, reverse=True)
        self.top_pairs = scores[: max(1, cfg.top_k)]
        return self.top_pairs
