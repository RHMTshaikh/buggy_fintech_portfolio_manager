"""
Portfolio Valuation Engine.
Calculates real-time Net Asset Value (NAV), unrealized PnL, and exposure metrics.
"""

import uuid
from decimal import Decimal
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.portfolio.models import Account, Position
from src.market_data.pricing import PricingEngine


@dataclass(frozen=True)
class PositionValuation:
    symbol: str
    quantity: Decimal
    average_cost_basis: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal


@dataclass(frozen=True)
class PortfolioValuation:
    account_id: uuid.UUID
    currency: str
    cash_balance: Decimal
    total_market_value: Decimal
    net_asset_value: Decimal  # Cash + Market Value
    total_unrealized_pnl: Decimal
    positions: list[PositionValuation]


class ValuationEngine:
    """Evaluates the live financial standing of an account."""

    def __init__(self, session: AsyncSession, pricing_engine: PricingEngine):
        self.session = session
        self.pricing_engine = pricing_engine

    async def compute_portfolio_nav(self, account_id: uuid.UUID) -> PortfolioValuation:
        """
        Calculates total equity by combining settled cash and live market prices
        for all open positions.
        """
        # Fetch account and active positions
        account_stmt = select(Account).where(Account.id == account_id)
        account_res = await self.session.execute(account_stmt)
        account = account_res.scalar_one_or_none()
        
        if not account:
            raise ValueError(f"Account {account_id} not found.")

        pos_stmt = select(Position).where(
            Position.account_id == account_id,
            Position.quantity > Decimal("0")
        )
        pos_res = await self.session.execute(pos_stmt)
        positions = pos_res.scalars().all()

        evaluated_positions: list[PositionValuation] = []
        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")

        # Gather quotes and compute per-position PnL
        for pos in positions:
            quote = await self.pricing_engine.get_validated_quote(pos.symbol)
            
            # Use bid price for conservative liquidation valuation
            current_price = quote.bid
            market_value = pos.quantity * current_price
            cost = pos.quantity * pos.average_cost_basis
            pnl = market_value - cost
            
            pnl_pct = (pnl / cost * Decimal("100")) if cost > Decimal("0") else Decimal("0")

            evaluated_positions.append(
                PositionValuation(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    average_cost_basis=pos.average_cost_basis,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=pnl,
                    unrealized_pnl_percent=pnl_pct.quantize(Decimal("0.01"))
                )
            )

            total_market_value += market_value
            total_cost_basis += cost

        nav = account.cash_balance + total_market_value
        total_pnl = total_market_value - total_cost_basis

        return PortfolioValuation(
            account_id=account.id,
            currency=account.currency,
            cash_balance=account.cash_balance,
            total_market_value=total_market_value,
            net_asset_value=nav,
            total_unrealized_pnl=total_pnl,
            positions=evaluated_positions
        )