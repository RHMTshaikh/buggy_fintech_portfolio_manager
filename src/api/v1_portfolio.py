"""
Portfolio API Router.
Handles read-only valuation queries and algorithmic rebalancing instructions.
"""

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, Body

from src.api.dependencies import get_current_account_id, get_valuation_engine, get_rebalance_engine
from src.portfolio.valuation import ValuationEngine, PortfolioValuation
from src.portfolio.rebalance import RebalanceEngine, OrderInstruction

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/nav", response_model=PortfolioValuation)
async def get_portfolio_nav(
    account_id: uuid.UUID = Depends(get_current_account_id),
    valuation_engine: ValuationEngine = Depends(get_valuation_engine),
):
    """Calculates real-time Net Asset Value and unrealized PnL."""
    return await valuation_engine.compute_portfolio_nav(account_id)


@router.post("/rebalance/instructions", response_model=list[OrderInstruction])
async def preview_rebalance(
    target_weights: dict[str, Decimal] = Body(
        ..., 
        example={"AAPL": "0.40", "MSFT": "0.60"},
        description="Target allocation weights summing to 1.0"
    ),
    account_id: uuid.UUID = Depends(get_current_account_id),
    rebalance_engine: RebalanceEngine = Depends(get_rebalance_engine),
):
    """
    Generates exact trade trajectories needed to realign the portfolio to target weights.
    Does NOT execute the trades (Safe Preview).
    """
    return await rebalance_engine.generate_rebalance_instructions(account_id, target_weights)