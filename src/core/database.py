"""
Database Persistence Architecture.
Configures SQLAlchemy 2.0 AsyncEngine, Session Factory, and Base Models.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
import uuid
from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.config import settings

# ---------------------------------------------------------------------------
# Async Engine & Session Factory Initialization
# ---------------------------------------------------------------------------

async_engine = create_async_engine(
    settings.async_database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_pre_ping=True,  # Proactively discards broken connections before giving to pool
    echo=settings.DB_ECHO_SQL,
)

AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,  # Essential for async SQLAlchemy to prevent detached instance errors
)


# ---------------------------------------------------------------------------
# Declarative Base & Audit Models
# ---------------------------------------------------------------------------

class Base(AsyncAttrs, DeclarativeBase):
    """Abstract declarative base enabling async attribute exploration."""
    pass


class TimestampMixin:
    """Provides common timestamp fields for database records."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=lambda: datetime.utcnow(),
        nullable=False,
    )


class OptimisticLockMixin:
    """
    Protects critical balance, position, and order updates from race conditions.
    SQLAlchemy increments version_id on every UPDATE.
    """
    version_id: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    __mapper_args__ = {
        "version_id_col": version_id,
    }


class UUIDPrimaryKeyMixin:
    """Uniform UUID v4 primary keys for distributed idempotency."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )


# ---------------------------------------------------------------------------
# FastApi Dependency Injection
# ---------------------------------------------------------------------------

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding isolated, transactional async sessions.
    Automatically rolls back on unhandled exceptions and cleans up on exit.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()