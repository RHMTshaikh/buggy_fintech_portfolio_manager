"""
Portfolio & Ledger Database Models.
Implements user accounts, asset holdings (Positions), and immutable Ledger Journals.
"""

from decimal import Decimal
import uuid
from sqlalchemy import ForeignKey, String, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.core.database import Base, TimestampMixin, OptimisticLockMixin, UUIDPrimaryKeyMixin


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRADE_SETTLEMENT = "TRADE_SETTLEMENT"
    FEE_ASSESSMENT = "FEE_ASSESSMENT"


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin, OptimisticLockMixin):
    """
    Represents a user's financial portfolio account.
    cash_balance is a fast-read materialized view of the underlying ledger,
    protected by optimistic concurrency control (version_id).
    """
    __tablename__ = "portfolio_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), 
        default=Decimal("0.0"), 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    positions: Mapped[list["Position"]] = relationship(
        "Position", back_populates="account", cascade="all, delete-orphan"
    )
    journals: Mapped[list["LedgerJournal"]] = relationship(
        "LedgerJournal", back_populates="account"
    )


class Position(Base, UUIDPrimaryKeyMixin, TimestampMixin, OptimisticLockMixin):
    """
    Represents a specific asset holding within an account.
    """
    __tablename__ = "portfolio_positions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"), 
        index=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), 
        default=Decimal("0.0"), 
        nullable=False
    )
    average_cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), 
        default=Decimal("0.0"), 
        nullable=False
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="positions")


class LedgerJournal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    An immutable record of a financial event (e.g., a trade or transfer).
    Groups multiple LedgerEntries into a single atomic business transaction.
    """
    __tablename__ = "portfolio_ledger_journals"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_accounts.id"), index=True, nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    reference_id: Mapped[str] = mapped_column(
        String(255), index=True, nullable=True, comment="e.g., external order ID"
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="journals")
    entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="journal", cascade="all, delete-orphan"
    )


class LedgerEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single movement of an asset (cash or security) within a Journal.
    Amounts are signed: positive for credits (inflows), negative for debits (outflows).
    """
    __tablename__ = "portfolio_ledger_entries"

    journal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_ledger_journals.id", ondelete="CASCADE"), 
        index=True, nullable=False
    )
    asset: Mapped[str] = mapped_column(String(20), nullable=False, comment="Symbol or Currency (e.g., USD, AAPL)")
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), nullable=False
    )

    # Relationships
    journal: Mapped["LedgerJournal"] = relationship("LedgerJournal", back_populates="entries")