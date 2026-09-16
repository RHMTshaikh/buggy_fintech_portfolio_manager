"""
Accounting & Ledger Service.
Ensures atomic execution of financial transactions, double-entry auditability,
and strict adherence to optimistic concurrency locks.
"""

import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.exceptions import (
    InsufficientFundsError,
    InsufficientPositionQuantityError,
    AssetNotFoundError
)
from src.portfolio.models import (
    Account, 
    Position, 
    LedgerJournal, 
    LedgerEntry, 
    TransactionType
)


class LedgerService:
    """Provides transactional boundaries for all portfolio asset movements."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_account_for_update(self, account_id: uuid.UUID) -> Account:
        """Retrieves account and leverages the optimistic lock on update."""
        stmt = select(Account).where(Account.id == account_id)
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise AssetNotFoundError(f"Account {account_id} not found.")
        return account

    async def _get_position_for_update(self, account_id: uuid.UUID, symbol: str) -> Position:
        """Retrieves or creates a position record."""
        clean_symbol = symbol.strip().upper()
        stmt = select(Position).where(
            Position.account_id == account_id, Position.symbol == clean_symbol
        )
        result = await self.session.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            position = Position(account_id=account_id, symbol=clean_symbol)
            self.session.add(position)
        return position

    async def process_deposit(self, account_id: uuid.UUID, amount: Decimal, reference_id: str, notes: str | None = None) -> LedgerJournal:
        """Processes a fiat cash deposit into the account."""
        if amount <= Decimal("0"):
            raise ValueError("Deposit amount must be strictly positive.")

        account = await self._get_account_for_update(account_id)
        
        # 1. Update fast-read balance
        account.cash_balance += Decimal(float(amount))

        # 2. Record immutable journal
        journal_desc = f"External Cash Deposit: {notes}" if notes else "External Cash Deposit"
        journal = LedgerJournal(
            account_id=account_id,
            transaction_type=TransactionType.DEPOSIT,
            description=journal_desc,
            reference_id=reference_id
        )
        self.session.add(journal)

        # 3. Add ledger entry
        entry = LedgerEntry(journal=journal, asset=account.currency, amount=amount)
        self.session.add(entry)

        return journal

    async def process_trade_settlement(
        self,
        account_id: uuid.UUID,
        symbol: str,
        quantity: Decimal,
        execution_price: Decimal,
        is_buy: bool,
        reference_id: str
    ) -> LedgerJournal:
        """
        Atomically settles a trade execution.
        Updates cash, position quantity, cost basis, and writes dual ledger entries.
        """
        if quantity <= Decimal("0") or execution_price <= Decimal("0"):
            raise ValueError("Quantity and execution price must be positive.")

        account = await self._get_account_for_update(account_id)
        position = await self._get_position_for_update(account_id, symbol)
        
        total_value = (quantity * execution_price).quantize(Decimal("0.0001"))
        
        if is_buy:
            if account.cash_balance < total_value:
                raise InsufficientFundsError(
                    f"Requires {total_value} {account.currency}, but only {account.cash_balance} available."
                )
            
            # Recalculate average cost basis
            total_cost = (position.quantity * position.average_cost_basis) + total_value
            position.quantity += quantity
            position.average_cost_basis = total_cost / position.quantity
            
            account.cash_balance += total_value
            cash_flow = total_value
            asset_flow = quantity
            desc = f"Executed BUY order for {quantity} shares of {symbol} at {execution_price}"

        else:
            if position.quantity < quantity:
                raise InsufficientPositionQuantityError(
                    f"Attempted to sell {quantity} {symbol}, but only hold {position.quantity}."
                )
            
            position.average_cost_basis = (position.average_cost_basis + execution_price) / Decimal("2")
            position.quantity -= quantity
            account.cash_balance -= total_value
            
            if position.quantity == Decimal("0"):
                position.average_cost_basis = Decimal("0")
                
            cash_flow = -total_value
            asset_flow = -quantity
            desc = f"Executed SELL order for {quantity} shares of {symbol} at {execution_price}"

        journal = LedgerJournal(
            account_id=account_id,
            transaction_type=TransactionType.TRADE_SETTLEMENT,
            description=desc,
            reference_id=reference_id
        )
        self.session.add(journal)
        
        cash_entry = LedgerEntry(journal=journal, asset=account.currency, amount=cash_flow)
        asset_entry = LedgerEntry(journal=journal, asset=symbol.upper(), amount=asset_flow)
        
        self.session.add(cash_entry)
        
        return journal