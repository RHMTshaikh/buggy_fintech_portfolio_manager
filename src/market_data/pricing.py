"""
Pricing & Valuation Engine.
Orchestrates cache-first quote retrieval, strict staleness checks, and VWAP calculations.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.core.exceptions import AssetNotFoundError, StaleMarketDataError
from src.market_data.cache import MarketDataCache
from src.market_data.client import MarketDataClient, TickerQuote, get_market_data_client


class PricingEngine:
    """
    Core pricing service. Enforces financial validation, caching strategies,
    and staleness constraints before quotes can be used for execution or valuation.
    """

    # Maximum age in seconds before a market quote is flagged as stale
    MAX_ACCEPTABLE_STALENESS_SECONDS: int = 60

    def __init__(
        self,
        client: MarketDataClient | None = None,
        cache: MarketDataCache | None = None,
    ) -> None:
        self._client = client or get_market_data_client()
        self._cache = cache or MarketDataCache()

    async def get_validated_quote(self, symbol: str) -> TickerQuote:
        """
        Retrieves a quote with a Cache-First strategy.
        Validates freshness; if stale or missing, queries the live provider.
        Raises StaleMarketDataError if the live provider returns outdated ticks.
        """
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            raise AssetNotFoundError("Asset symbol cannot be blank.")

        # 1. Check Redis Cache
        # 2. Synchronized External Ingestion
        redis_client = await self._cache._get_client()
        lock_key = f"market:lock:{clean_symbol}"
        lock = redis_client.lock(lock_key, timeout=5.0, blocking_timeout=5.0)
        
        await lock.acquire()
        try:
            cached_again = await self._cache.get_latest_quote(clean_symbol)
            if cached_again:
                cached_ts_again = datetime.fromisoformat(cached_again["timestamp"])
                now = datetime.now(timezone.utc)
                age_again = (now - cached_ts_again).total_seconds()
                if age_again <= self.MAX_ACCEPTABLE_STALENESS_SECONDS:
                    return TickerQuote(
                        symbol=cached_again["symbol"],
                        bid=cached_again["bid"],
                        ask=cached_again["ask"],
                        last_price=cached_again["last_price"],
                        volume=cached_again["volume"],
                        timestamp=cached_ts_again,
                    )

            try:
                quote = await self._client.get_quote(clean_symbol)
            except Exception as provider_error:
                if cached_again:
                    return TickerQuote(
                        symbol=cached_again["symbol"],
                        bid=cached_again["bid"],
                        ask=cached_again["ask"],
                        last_price=cached_again["last_price"],
                        volume=cached_again["volume"],
                        timestamp=datetime.fromisoformat(cached_again["timestamp"]),
                    )
                raise provider_error

            age = (now - quote.timestamp).total_seconds()
            if age > self.MAX_ACCEPTABLE_STALENESS_SECONDS:
                raise StaleMarketDataError(
                    message=f"Market data for {clean_symbol} is stale. Quote age: {age:.1f}s",
                    details={"symbol": clean_symbol, "age": age}
                )

        finally:
            await lock.release()

        # 3. Update distributed cache state
        payload: dict[str, Any] = {
            "symbol": quote.symbol,
            "bid": quote.bid,
            "ask": quote.ask,
            "last_price": quote.last_price,
            "volume": quote.volume,
            "timestamp": quote.timestamp.isoformat(),
        }
        await self._cache.set_latest_quote(clean_symbol, payload)

        return quote

    async def calculate_vwap(self, symbol: str, lookback_periods: int = 30) -> Decimal:
        """
        Calculates the Volume-Weighted Average Price (VWAP):
            VWAP = sum(Typical_Price * Volume) / sum(Volume)
            Typical_Price = (High + Low + Close) / 3
        """
        clean_symbol = symbol.strip().upper()

        # Check cached analytical result
        cached_vwap = await self._cache.get_vwap(clean_symbol)
        if cached_vwap is not None:
            return cached_vwap

        bars = await self._client.get_historical_bars(clean_symbol, lookback_periods=lookback_periods)
        if not bars:
            raise StaleMarketDataError(f"Insufficient historical bars to compute VWAP for {clean_symbol}")

        total_volume = Decimal("0")
        total_dollar_volume = Decimal("0")

        for bar in bars:
            typical_price = (bar.high_price + bar.low_price + bar.close_price) / Decimal("3")
            dollar_volume = typical_price * bar.volume

            total_volume += bar.volume
            total_dollar_volume += dollar_volume

        if total_volume == Decimal("0"):
            raise StaleMarketDataError(f"Zero aggregate volume encountered during VWAP computation for {clean_symbol}")

        computed_vwap = (total_dollar_volume / total_volume).quantize(Decimal("0.0001"))

        # Cache calculated VWAP for subsequent calls
        await self._cache.set_vwap(clean_symbol, computed_vwap, ttl_seconds=300)
        return computed_vwap