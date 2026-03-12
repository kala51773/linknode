from dataclasses import dataclass
import math

@dataclass
class CostResult:
    net_pnl: float
    fee_usd: float
    slippage_usd: float

class SimulationCostModel:
    """PRD M3 Cost and impact slippage modeling."""
    
    def __init__(self, maker_fee_bps: float = 0.02, taker_fee_bps: float = 0.05, 
                 market_impact_bps_per_100k: float = 1.0):
        self.maker_bps = maker_fee_bps
        self.taker_bps = taker_fee_bps
        self.impact_bps = market_impact_bps_per_100k
        
    def execute_cost(self, notional_usd: float, is_maker: bool) -> float:
        """Returns positive fee amount in USD."""
        bps = self.maker_bps if is_maker else self.taker_bps
        return notional_usd * (bps / 10000.0)
        
    def estimate_market_impact(self, notional_usd: float) -> float:
        """Estimates slippage relative to mid price for aggressive orders."""
        # sqrt(size) based impact model proxy
        if notional_usd <= 0: return 0.0
        
        impact_bps = self.impact_bps * math.sqrt(notional_usd / 100_000.0)
        slippage_usd = (impact_bps / 10000.0) * notional_usd
        return slippage_usd
        
    def evaluate_trade_pnl(self, gross_pnl: float, notional_usd: float, is_maker: bool) -> CostResult:
        fee = self.execute_cost(notional_usd, is_maker)
        
        slippage = 0.0
        if not is_maker:
            slippage = self.estimate_market_impact(notional_usd)
            
        net = gross_pnl - fee - slippage
        
        return CostResult(
            net_pnl=net,
            fee_usd=fee,
            slippage_usd=slippage
        )
