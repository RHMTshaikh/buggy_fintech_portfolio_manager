"""
Trading Database Models.
Implements the Order Book state machine and Execution receipts.
"""

from decimal import Decimal
import enum
import uuid
from sqlalchemy import ForeignKey, String, Numeric, Enum as SQLEnum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, OptimisticLockMixin, UUIDPrimaryKeyMixin


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"        # Awaiting risk checks
    REJECTED = "REJECTED"      # Failed risk or validation
    OPEN = "OPEN"              # Resting in the order book
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"          # Terminal state
    CANCELED = "CANCELED"      # Terminal state


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin, OptimisticLockMixin):
    """
    Represents a client's request to buy or sell an asset.
    Protected by optimistic locking to prevent concurrent double-fills.
    """
    __tablename__ = "trading_orders"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"), 
        index=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    side: Mapped[OrderSide] = mapped_column(SQLEnum(OrderSide), nullable=False)
    type: Mapped[OrderType] = mapped_column(SQLEnum(OrderType), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False, index=True
    )
    
    requested_quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), nullable=False
    )
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), default=Decimal("0.0"), nullable=False
    )
    
    # Conditional pricing limits based on OrderType
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(precision=36, scale=18), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(precision=36, scale=18), nullable=True)

    # Relationships
    executions: Mapped[list["TradeExecution"]] = relationship(
        "TradeExecution", back_populates="order", cascade="all, delete-orphan"
    )


class TradeExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Immutable receipt of a market fill. 
    Multiple executions can map to a single order (partial fills).
    """
    __tablename__ = "trading_executions"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_orders.id", ondelete="CASCADE"), 
        index=True, nullable=False
    )
    execution_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=36, scale=18), nullable=False
    )
    broker_reference_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="executions")