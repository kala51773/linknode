from dataclasses import dataclass

import numpy as np
import pandas as pd

@dataclass
class PairStats:
    corr_30d: float
    r2_6h: float
    beta: float
    beta_instability: float
    half_life_seconds: float
    mean_spread: float

class CointegrationStatsModel:
    """Computes Rolling Beta, Correlation, R2 and Half-life for Discover Engine."""
    
    def __init__(self, history_limit: int = 20000):
        self.history_limit = history_limit
        
    def calculate_stats(self, prices_a: pd.Series, prices_b: pd.Series) -> PairStats:
        """
        Prices should be aligned time-series of log prices.
        """
        aligned_a, aligned_b = self._align(prices_a, prices_b)
        if len(aligned_a) < 100 or len(aligned_b) < 100:
            return PairStats(0, 0, 1.0, 1.0, 0, 0)

        log_a = np.log(aligned_a)
        log_b = np.log(aligned_b)

        corr_30d = float(log_a.corr(log_b))

        var_a = float(np.var(log_a))
        if var_a > 0:
            beta = float(np.cov(log_a, log_b)[0, 1] / var_a)
        else:
            beta = 1.0

        spread = log_b - beta * log_a
        mean_spread = float(spread.mean())

        # R2 of log_b = alpha + beta * log_a
        fitted = beta * log_a + mean_spread
        resid = log_b - fitted
        ss_res = float(np.sum(np.square(resid)))
        ss_tot = float(np.sum(np.square(log_b - float(log_b.mean()))))
        r2_6h = 0.0 if ss_tot <= 0 else float(max(0.0, min(1.0, 1 - ss_res / ss_tot)))

        half_life = self._compute_half_life(spread)
        beta_instability = self._compute_beta_instability(log_a, log_b)

        return PairStats(
            corr_30d=corr_30d,
            r2_6h=r2_6h,
            beta=beta,
            beta_instability=beta_instability,
            half_life_seconds=half_life,
            mean_spread=mean_spread,
        )

    def _align(self, prices_a: pd.Series, prices_b: pd.Series) -> tuple[pd.Series, pd.Series]:
        series_a = prices_a.astype(float).tail(self.history_limit)
        series_b = prices_b.astype(float).tail(self.history_limit)
        merged = pd.concat([series_a.rename("a"), series_b.rename("b")], axis=1).dropna()
        if merged.empty:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        filtered = merged[(merged["a"] > 0) & (merged["b"] > 0)]
        if filtered.empty:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        return filtered["a"], filtered["b"]

    @staticmethod
    def _compute_half_life(spread: pd.Series) -> float:
        lag = spread.shift(1).dropna()
        if lag.empty:
            return 9999.0
        delta = (spread - lag).dropna()
        lag = lag.reindex(delta.index)
        var_lag = float(np.var(lag))
        if var_lag <= 0:
            return 9999.0
        beta = float(np.cov(lag, delta)[0, 1] / var_lag)
        if beta >= 0:
            return 9999.0
        # Assumed 1-second bars for now.
        return float(np.log(2.0) / -beta)

    @staticmethod
    def _compute_beta_instability(log_a: pd.Series, log_b: pd.Series) -> float:
        n = len(log_a)
        window = max(20, min(120, n // 5))
        if n < window + 5:
            return 1.0

        a = log_a.to_numpy()
        b = log_b.to_numpy()
        betas: list[float] = []
        for end in range(window, n + 1):
            aa = a[end - window:end]
            bb = b[end - window:end]
            var_a = float(np.var(aa))
            if var_a <= 0:
                continue
            beta = float(np.cov(aa, bb)[0, 1] / var_a)
            if np.isfinite(beta):
                betas.append(beta)
        if len(betas) < 2:
            return 1.0
        mean_beta = float(np.mean(betas))
        std_beta = float(np.std(betas))
        if abs(mean_beta) < 1e-9:
            return 1.0
        return float(min(1.0, std_beta / abs(mean_beta)))
