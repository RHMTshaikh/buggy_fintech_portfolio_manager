"""
Algorithmic Portfolio Rebalancing.
Generates execution instructions to align a portfolio to target asset weights.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from src.portfolio.valuation import ValuationEngine, PortfolioValuation


@dataclass(frozen=True)
class OrderInstruction:
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: Decimal
    estimated_value: Decimal


class RebalanceEngine:
    """Calculates trade trajectories necessary to achieve target model weights."""

    def __init__(self, valuation_engine: ValuationEngine):
        self.valuation_engine = valuation_engine

    async def generate_rebalance_instructions(
        self, 
        account_id: uuid.UUID, 
        target_weights: Mapping[str, Decimal]
    ) -> list[OrderInstruction]:
        """
        Compares current NAV exposure to `target_weights` (e.g. {"AAPL": 0.4, "MSFT": 0.6})
        and generates required trade instructions.
        """
        # Validate weights sum to <= 1.0 (100%)
        total_weight = sum(target_weights.values())
        if total_weight > Decimal("1.0"):
            raise ValueError(f"Target weights exceed 100% (sum: {total_weight})")

        # Get current valuation state
        valuation: PortfolioValuation = await self.valuation_engine.compute_portfolio_nav(account_id)
        nav = valuation.net_asset_value

        current_holdings = {pos.symbol: pos for pos in valuation.positions}
        instructions: list[OrderInstruction] = []

        # 1. Identify SELL instructions (Overweight positions or full liquidations)
        for symbol, position in current_holdings.items():
            target_weight = target_weights.get(symbol, Decimal("0.0"))
            target_value = nav * target_weight
            
            if position.market_value > target_value:
                # Need to reduce position
                value_to_sell = position.market_value - target_value
                qty_to_sell = (value_to_sell / position.current_price).quantize(Decimal("0.00001"))
                
                if qty_to_sell > Decimal("0"):
                    instructions.append(
                        OrderInstruction(
                            symbol=symbol,
                            action="SELL",
                            quantity=qty_to_sell,
                            estimated_value=value_to_sell
                        )
                    )

        # 2. Identify BUY instructions (Underweight positions)
        for symbol, target_weight in target_weights.items():
            target_value = nav * target_weight
            current_pos = current_holdings.get(symbol)
            
            current_value = current_pos.market_value if current_pos else Decimal("0.0")
            
            if current_value < target_value:
                value_to_buy = target_value - current_value
                
                # Fetch price if we don't hold the asset yet
                if current_pos:
                    price = current_pos.current_price
                else:
                    quote = await self.valuation_engine.pricing_engine.get_validated_quote(symbol)
                    price = quote.ask # Use ask for conservative buy estimation

                qty_to_buy = (value_to_buy / price).quantize(Decimal("0.00001"))
                
                if qty_to_buy > Decimal("0"):
                    instructions.append(
                        OrderInstruction(
                            symbol=symbol,
                            action="BUY",
                            quantity=qty_to_buy,
                            estimated_value=value_to_buy
                        )
                    )

        return instructions