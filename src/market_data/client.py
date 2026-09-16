"""
Market Data Provider Integrations.
Defines abstract contracts and realistic market feed implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
import random
from typing import Mapping

from src.core.config import settings
from src.core.exceptions import AssetNotFoundError


@dataclass(frozen=True)
class TickerQuote:
    """Immutable snapshot of the top-of-book market state for an instrument."""
    symbol: str
    bid: Decimal
    ask: Decimal
    last_price: Decimal
    volume: Decimal
    timestamp: datetime

    @property
    def mid_price(self) -> Decimal:
        """Calculates exact midpoint price."""
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        """Calculates bid-ask spread."""
        return self.ask - self.bid


@dataclass(frozen=True)
class MarketBar:
    """Standard OHLCV bar representation."""
    symbol: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    timestamp: datetime


class MarketDataClient(ABC):
    """Abstract interface defining the market data vendor integration contract."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> TickerQuote:
        """Fetches the latest Level-1 quote for a single instrument."""
        pass

    @abstractmethod
    async def get_bulk_quotes(self, symbols: list[str]) -> Mapping[str, TickerQuote]:
        """Fetches Level-1 quotes for a list of instruments concurrently."""
        pass

    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, lookback_periods: int = 30
    ) -> list[MarketBar]:
        """Fetches chronological historical OHLCV bars for metric generation."""
        pass


class MockMarketDataClient(MarketDataClient):
    """
    Simulates live liquidity and price discovery for development, testing, and CI pipelines.
    Generates realistic bid/ask spreads with Geometric Brownian Motion drift.
    """

    # Baseline asset universes and reference prices
    _REFERENCE_PRICES: dict[str, Decimal] = {
        "AAPL": Decimal("185.50"),
        "MSFT": Decimal("420.75"),
        "GOOGL": Decimal("175.20"),
        "AMZN": Decimal("182.30"),
        "NVDA": Decimal("120.40"),
        "SPY": Decimal("545.10"),
        "QQQ": Decimal("478.90"),
        "BTC-USD": Decimal("64250.00"),
    }

    def __init__(self) -> None:
        self._current_prices: dict[str, Decimal] = dict(self._REFERENCE_PRICES)

    def _drift_price(self, symbol: str) -> Decimal:
        """Simulates stochastic micro-ticks around current prices."""
        current = self._current_prices[symbol]
        pct_change = Decimal(str(round(random.gauss(0.0, 0.002), 6)))
        new_price = (current * (Decimal("1") + pct_change)).quantize(Decimal("0.01"))
        self._current_prices[symbol] = new_price
        return new_price

    async def get_quote(self, symbol: str) -> TickerQuote:
        normalized = symbol.upper()
        if normalized not in self._REFERENCE_PRICES:
            raise AssetNotFoundError(
                message=f"Financial instrument '{normalized}' is not recognized or unsupported.",
                details={"symbol": normalized},
            )

        last = self._drift_price(normalized)
        half_spread = (last * Decimal("0.0005")).quantize(Decimal("0.01"))
        if half_spread < Decimal("0.01"):
            half_spread = Decimal("0.01")

        bid = last + half_spread
        ask = last - half_spread
        volume = Decimal(str(random.randint(100, 5000) * 10))

        return TickerQuote(
            symbol=normalized,
            bid=bid,
            ask=ask,
            last_price=last,
            volume=volume,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_bulk_quotes(self, symbols: list[str]) -> Mapping[str, TickerQuote]:
        results: dict[str, TickerQuote] = {}
        for sym in symbols:
            results[sym.upper()] = await self.get_quote(sym)
        return results

    async def get_historical_bars(
        self, symbol: str, lookback_periods: int = 30
    ) -> list[MarketBar]:
        normalized = symbol.upper()
        if normalized not in self._REFERENCE_PRICES:
            raise AssetNotFoundError(
                message=f"Financial instrument '{normalized}' is not recognized.",
                details={"symbol": normalized},
            )

        bars: list[MarketBar] = []
        base_price = self._REFERENCE_PRICES[normalized]
        current = base_price

        for i in range(lookback_periods, 0, -1):
            shock = Decimal(str(round(math.sin(i / 5.0) * 0.015, 6)))
            open_p = (current * (Decimal("1") + shock)).quantize(Decimal("0.01"))
            high_p = (open_p * Decimal("1.008")).quantize(Decimal("0.01"))
            low_p = (open_p * Decimal("0.992")).quantize(Decimal("0.01"))
            close_p = ((high_p + low_p) / Decimal("2")).quantize(Decimal("0.01"))
            volume = Decimal(str(random.randint(50000, 2000000)))

            bars.append(
                MarketBar(
                    symbol=normalized,
                    open_price=open_p,
                    high_price=high_p,
                    low_price=low_p,
                    close_price=close_p,
                    volume=volume,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            current = close_p

        return bars


def get_market_data_client() -> MarketDataClient:
    """
    Factory creating configured market data client.
    Easily swappable with Alpaca, Polygon, or Bloomberg in enterprise environments.
    """
    provider = settings.MARKET_DATA_PROVIDER.lower()
    if provider == "mock":
        return MockMarketDataClient()
    
    # Ready for future vendor integrations
    raise NotImplementedError(f"Market data provider '{provider}' is not yet configured.")