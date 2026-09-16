"""
Market Data Redis Caching Layer.
Provides high-performance, asynchronous tick and quote caching with sub-millisecond retrieval.
"""

import json
from decimal import Decimal
from typing import Any
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from src.core.config import settings

# Global async connection pool initialized lazily
_redis_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """Initializes and returns a singleton Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    """Yields a managed Redis client instance from the shared connection pool."""
    pool = ConnectionPool.from_url(
        settings.redis_url,
        decode_responses=True
    )
    return aioredis.Redis(connection_pool=pool)


async def close_redis_pool() -> None:
    """Gracefully drains and closes the Redis connection pool on application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder preserving Decimal precision during Redis serialization."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class MarketDataCache:
    """
    Manages Redis key lifecycle for market quotes, order books, and calculated statistics.
    """

    DEFAULT_QUOTE_TTL_SECONDS: int = 15
    DEFAULT_BAR_TTL_SECONDS: int = 3600

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client

    async def _get_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    @staticmethod
    def _quote_key(symbol: str) -> str:
        return f"market:quote{symbol.upper()}"

    @staticmethod
    def _vwap_key(symbol: str) -> str:
        return f"market:vwap{symbol.upper()}"

    async def set_latest_quote(
        self,
        symbol: str,
        quote_payload: dict[str, Any],
        ttl_seconds: int = DEFAULT_QUOTE_TTL_SECONDS,
    ) -> None:
        """Serializes and caches the latest bid/ask/last quote for a symbol."""
        client = await self._get_client()
        key = self._quote_key(symbol)
        serialized = json.dumps(quote_payload, cls=DecimalEncoder)
        await client.set(key, serialized, ex=ttl_seconds)

    async def get_latest_quote(self, symbol: str) -> dict[str, Any] | None:
        """Retrieves and deserializes the cached quote, returning None if expired or absent."""
        client = await self._get_client()
        raw_data = await client.get(self._quote_key(symbol))
        if not raw_data:
            return None
        
        parsed = json.loads(raw_data)
        # Restore Decimal types from serialized strings
        for field in ("bid", "ask", "last_price", "volume"):
            if field in parsed and parsed[field] is not None:
                parsed[field] = Decimal(str(parsed[field]))
        return parsed

    async def set_vwap(self, symbol: str, vwap: Decimal, ttl_seconds: int = DEFAULT_BAR_TTL_SECONDS) -> None:
        """Caches computed VWAP metrics."""
        client = await self._get_client()
        key = self._vwap_key(symbol)
        await client.set(key, str(vwap), ex=ttl_seconds)

    async def get_vwap(self, symbol: str) -> Decimal | None:
        """Fetches cached VWAP if available."""
        client = await self._get_client()
        raw_val = await client.get(self._vwap_key(symbol))
        return Decimal(raw_val) if raw_val is not None else None

    async def invalidate_symbol(self, symbol: str) -> None:
        """Purges cached quotes and analytics for a specific instrument."""
        client = await self._get_client()
        await client.delete(self._quote_key(symbol), self._vwap_key(symbol))