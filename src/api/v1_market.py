"""
Market Data API Router.
Serves real-time quotes, spreads, and VWAP analytics.
"""

from decimal import Decimal
from fastapi import APIRouter, Depends

from src.api.dependencies import get_pricing_engine
from src.market_data.pricing import PricingEngine
from src.market_data.client import TickerQuote

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get("/quote/{symbol}", response_model=TickerQuote)
async def get_live_quote(
    symbol: str,
    pricing_engine: PricingEngine = Depends(get_pricing_engine),
):
    """Fetches the latest Level-1 quote (Bid, Ask, Last) with caching & staleness validation."""
    return await pricing_engine.get_validated_quote(symbol)


@router.get("/vwap/{symbol}", response_model=dict[str, Decimal | str])
async def get_vwap(
    symbol: str,
    lookback: int = 30,
    pricing_engine: PricingEngine = Depends(get_pricing_engine),
):
    """Calculates Volume Weighted Average Price (VWAP) over a historical lookback window."""
    vwap = await pricing_engine.calculate_vwap(symbol, lookback_periods=lookback)
    return {"symbol": symbol.upper(), "vwap": vwap}