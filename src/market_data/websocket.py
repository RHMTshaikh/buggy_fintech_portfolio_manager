"""
WebSocket & Streaming Market Data Broadcast Engine.
Uses Redis Pub/Sub for horizontal scaling across multiple application instances.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any
import redis.asyncio as aioredis

from src.market_data.cache import DecimalEncoder, get_redis_client
from src.market_data.client import TickerQuote


class MarketDataStreamManager:
    """
    Manages in-memory client subscriptions and bridges them to distributed Redis Pub/Sub channels.
    Allows multiple worker processes to broadcast quotes to connected frontend clients.
    """

    CHANNEL_PREFIX: str = "market:stream:"

    def __init__(self) -> None:
        # Map: symbol -> set of local asyncio.Queue instances
        self._local_subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._redis_client: aioredis.Redis | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._is_running: bool = False

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis_client is None:
            self._redis_client = await get_redis_client()
        return self._redis_client

    async def publish_tick(self, quote: TickerQuote) -> None:
        """
        Publishes a new market tick to the distributed Redis channel.
        Any worker node subscribed to this symbol will receive and broadcast it.
        """
        client = await self._get_redis()
        channel = f"{self.CHANNEL_PREFIX}{quote.symbol.upper()}"
        
        payload = {
            "symbol": quote.symbol,
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "last_price": str(quote.last_price),
            "volume": str(quote.volume),
            "timestamp": quote.timestamp.isoformat(),
        }
        await client.publish(channel, json.dumps(payload, cls=DecimalEncoder))

    async def subscribe(self, symbols: list[str], client_token: str | None = None) -> AsyncGenerator[dict[str, Any], None]:
        """
        Subscribes a client to real-time quotes and optional private trade notifications.
        Yields normalized payloads as they arrive.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        clean_symbols = [s.strip().upper() for s in symbols]

        # Register for public market data
        for s in clean_symbols:
            self._local_subscribers[s].add(queue)
            
        # Register for private execution notifications if a token is provided
        # Authentication is assumed to be handled upstream by the load balancer
        if client_token:
            self._local_subscribers[f"private:{client_token}"].add(queue)

        try:
            while True:
                # Wait for next incoming tick
                tick = await queue.get()
                yield tick
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            # Clean up subscriber references
            for s in clean_symbols:
                self._local_subscribers[s].discard(queue)
                if not self._local_subscribers[s]:
                    self._local_subscribers.pop(s, None)

    async def start_redis_listener(self) -> None:
        """
        Background listener task subscribing to Redis Pub/Sub wildcard channels.
        Pushes received ticks to local listener queues.
        """
        if self._is_running:
            return

        self._is_running = True
        client = await self._get_redis()
        pubsub = client.pubsub()
        await pubsub.psubscribe(f"{self.CHANNEL_PREFIX}*")

        try:
            while self._is_running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "pmessage":
                    raw_data = message.get("data")
                    if raw_data:
                        tick_dict = json.loads(raw_data)
                        sym = tick_dict.get("symbol", "").upper()
                        
                        # Fan out to all local queues monitoring this symbol
                        target_queues = list(self._local_subscribers.get(sym, []))
                        for q in target_queues:
                            if not q.full():
                                q.put_nowait(tick_dict)
                await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.punsubscribe(f"{self.CHANNEL_PREFIX}*")
            await pubsub.close()
            self._is_running = False

    def stop(self) -> None:
        """Stops the Redis background listener."""
        self._is_running = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()


# Singleton stream manager for application-wide broadcasting
stream_manager = MarketDataStreamManager()