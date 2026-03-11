import unittest
import math
from wickhunter.strategy.alpha import PairStats, ResidualModel, FairValue

class TestResidualModel(unittest.TestCase):
    def test_residual_calculation(self):
        stats = PairStats(beta=0.8, gamma=0.5, corr=0.85, r2=0.72, beta_instability=0.1, liquidity_penalty=0.0)
        model = ResidualModel(stats=stats, model_weight=1.0)
        
        # p_B_local = 100
        # p_A = 120
        # p_sector = 1.05
        # spread_t = log(100) - 0.8 * log(120) - 0.5 * log(1.05)
        # fair_B_t = exp(0.8 * log(120) + 0.5 * log(1.05))
        
        fv = model.compute_fair_value(p_B_local=100.0, p_A=120.0, p_sector=1.05)
        
        expected_log_fair = 0.8 * math.log(120.0) + 0.5 * math.log(1.05)
        expected_fair = math.exp(expected_log_fair)
        expected_spread = math.log(100.0) - expected_log_fair
        
        self.assertAlmostEqual(fv.fair_price, expected_fair, places=4)
        self.assertAlmostEqual(fv.spread, expected_spread, places=4)
        self.assertAlmostEqual(fv.gap, (100.0 / expected_fair) - 1.0, places=4)
        
        expected_score = 0.4*0.85 + 0.35*0.72 - 0.15*0.1 - 0.10*0.0
        self.assertAlmostEqual(fv.score, expected_score, places=4)

    def test_weighted_cross_venue_fair(self):
        stats = PairStats(beta=0.8, gamma=0.5, corr=0.85, r2=0.72, beta_instability=0.1, liquidity_penalty=0.0)
        model = ResidualModel(stats=stats, model_weight=0.6)
        
        expected_log_fair = 0.8 * math.log(120.0) + 0.5 * math.log(1.05)
        expected_model_fair = math.exp(expected_log_fair)
        cross_venue_fair = 105.0
        
        fv = model.compute_fair_value(p_B_local=100.0, p_A=120.0, p_sector=1.05, cross_venue_fair=cross_venue_fair)
        
        expected_hybrid_fair = 0.4 * cross_venue_fair + 0.6 * expected_model_fair
        self.assertAlmostEqual(fv.fair_price, expected_hybrid_fair, places=4)
