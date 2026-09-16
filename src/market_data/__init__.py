"""
Market Data Bounded Context.
Exposes public interfaces, pricing engines, and caching services.
"""

from src.market_data.cache import MarketDataCache, close_redis_pool
from src.market_data.client import (
    MarketBar,
    MarketDataClient,
    MockMarketDataClient,
    TickerQuote,
    get_market_data_client,
)
from src.market_data.pricing import PricingEngine
from src.market_data.websocket import MarketDataStreamManager, stream_manager

__all__ = [
    "MarketDataCache",
    "close_redis_pool",
    "MarketDataClient",
    "MockMarketDataClient",
    "TickerQuote",
    "MarketBar",
    "get_market_data_client",
    "PricingEngine",
    "MarketDataStreamManager",
    "stream_manager",
]