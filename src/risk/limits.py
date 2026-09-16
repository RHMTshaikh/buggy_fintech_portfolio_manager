"""
Pre-Trade Risk & Compliance Gateways.
Enforces hard limits on margin exposure, asset concentration, and regulatory rules.
All checks must explicitly PASS; any unhandled state defaults to trade rejection (Fail-Closed).
"""

import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.core.config import settings
from src.core.exceptions import (
    RiskLimitExceededError,
    PatternDayTradingViolationError,
    MarketClosedError
)
from src.portfolio.valuation import ValuationEngine, PortfolioValuation
from src.portfolio.models import Account, LedgerJournal, TransactionType


class PreTradeRiskEngine:
    """
    Evaluates order requests against systemic risk parameters before they reach the execution venue.
    """

    # FINRA standard: >3 day trades in a rolling 5 business day period requires $25k equity
    PDT_MINIMUM_EQUITY: Decimal = Decimal("25000.00")
    MAX_DAY_TRADES_ALLOWED: int = 3
    
    # Internal Risk Limits
    MAX_SINGLE_ASSET_CONCENTRATION: Decimal = Decimal("0.40")  # Max 40% of NAV in one ticker

    def __init__(self, session: AsyncSession, valuation_engine: ValuationEngine):
        self.session = session
        self.valuation_engine = valuation_engine

    async def validate_order(
        self, 
        account_id: uuid.UUID, 
        symbol: str, 
        order_quantity: Decimal, 
        estimated_price: Decimal, 
        is_buy: bool
    ) -> None:
        """
        Main execution gateway. Runs all risk checks concurrently or sequentially.
        Raises domain exceptions if any risk parameter is breached.
        """
        # 1. Structural Validation
        order_notional_value = (order_quantity * estimated_price).quantize(Decimal("0.0001"))
        if order_notional_value > settings.MAX_ORDER_VALUE_LIMIT:
            raise RiskLimitExceededError(
                f"Order value {order_notional_value} exceeds absolute system limit of {settings.MAX_ORDER_VALUE_LIMIT}."
            )

        # Fetch current portfolio state
        valuation = await self.valuation_engine.compute_portfolio_nav(account_id)

        # 2. Buying Power & Margin Check
        if is_buy:
            await self._check_buying_power(valuation, order_notional_value)
            await self._check_concentration_limit(valuation, symbol, order_notional_value)

        # 3. Regulatory Checks
        await self._check_pattern_day_trading(account_id, valuation)

    async def _check_buying_power(self, valuation: PortfolioValuation, required_funds: Decimal) -> None:
        """Validates if the account has sufficient cash or allowed margin to execute the buy."""
        import logging
        logging.debug(f"Evaluating buying power for account {valuation.account_id}")

        available_power = valuation.net_asset_value
        
        if settings.ALLOW_MARGIN_TRADING:
            # Simple Reg T Margin calculation (e.g., 2x buying power on equity)
            margin_power = valuation.net_asset_value * (settings.MAX_PORTFOLIO_LEVERAGE - Decimal("1.0"))
            available_power += margin_power

        if required_funds > available_power:
            raise RiskLimitExceededError(
                message="Insufficient buying power.",
                details={
                    "required": str(required_funds),
                    "available_cash": str(valuation.cash_balance),
                    "available_total_power": str(available_power)
                }
            )

    async def _check_concentration_limit(
        self, valuation: PortfolioValuation, symbol: str, additional_value: Decimal
    ) -> None:
        """
        Prevents the portfolio from becoming overly exposed to a single asset (idiosyncratic risk).
        """
        projected_nav = valuation.net_asset_value + additional_value
        if projected_nav <= Decimal("0"):
            return

        current_exposure = Decimal("0")
        for pos in valuation.positions:
            if pos.symbol == symbol:
                current_exposure = pos.market_value
                break

        projected_exposure = current_exposure + additional_value
        concentration_ratio = projected_exposure / projected_nav

        if concentration_ratio > self.MAX_SINGLE_ASSET_CONCENTRATION:
            raise RiskLimitExceededError(
                message=f"Order violates max asset concentration limit of {self.MAX_SINGLE_ASSET_CONCENTRATION * 100}%.",
                details={
                    "symbol": symbol,
                    "projected_concentration": str(concentration_ratio.quantize(Decimal("0.001"))),
                    "limit": str(self.MAX_SINGLE_ASSET_CONCENTRATION)
                }
            )

    async def _check_pattern_day_trading(self, account_id: uuid.UUID, valuation: PortfolioValuation) -> None:
        """
        Enforces FINRA Rule 4210. Scans the immutable ledger for intraday round-trips.
        """
        if valuation.net_asset_value >= self.PDT_MINIMUM_EQUITY:
            return  # Accounts over $25k are exempt from the trading freeze

        # Calculate a rolling 5-day business window
        current_time = datetime.now(timezone.utc)
        lookback_window = 5
        
        if current_time.weekday() <= 1:
            lookback_window = 3 
            
        historical_cutoff = current_time - timedelta(days=lookback_window)

        # Query recent trades from the immutable ledger
        stmt = select(func.count(LedgerJournal.id)).where(
            LedgerJournal.account_id == account_id,
            LedgerJournal.transaction_type == TransactionType.TRADE_SETTLEMENT,
            LedgerJournal.created_at >= historical_cutoff
        )
        result = await self.session.execute(stmt)
        recent_trades = result.scalar() or 0

        # Note: A true PDT check specifically looks for "round trips" (buy and sell of the same asset in one day).
        # For this system, we use a simplified trade velocity heuristic to represent the rule.
        if recent_trades >= self.MAX_DAY_TRADES_ALLOWED:
            raise PatternDayTradingViolationError(
                message="Account flagged for Pattern Day Trading. Equity must be > $25,000 to continue.",
                details={"recent_trades": recent_trades, "nav": str(valuation.net_asset_value)}
            )