"""
Global Configuration & Environment Management.
Uses Pydantic v2 Settings for strict runtime validation.
"""

from decimal import Decimal
from typing import Literal
from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment & Telemetry
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    PROJECT_NAME: str = "Fintech Portfolio Manager"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Security & Cryptography
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        description="Master cryptographic key used for JWT signing and token generation",
    )
    ENCRYPTION_KEY: str = Field(
        default="U2VjdXJlQnl0ZXNGZXJuZXRLZXlGb3JGaW50ZWNoUG9ydGZvbGlvMTI=", # Exactly 32 decoded bytes / 44 chars
        description="Base64-encoded 32-byte key for Fernet symmetric encryption of broker credentials",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database (PostgreSQL with asyncpg)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "portfolio_admin"
    POSTGRES_PASSWORD: str = "secure_dev_password"
    POSTGRES_DB: str = "fintech_portfolio"
    
    # SQLAlchemy Connection Pool Tuning
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_ECHO_SQL: bool = False

    # Redis (Market Data Cache & Idempotency)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_TIMEOUT_SECONDS: int = 2

    # Broker & External Market Data Integrations
    MARKET_DATA_PROVIDER: Literal["mock", "alpaca", "polygon", "bloomberg"] = "mock"
    MARKET_DATA_API_KEY: str = "mock-market-key"
    MARKET_DATA_SECRET_KEY: str = "mock-market-secret"
    BROKER_SANDBOX: bool = True

    # Trading & Risk Guardrails
    DEFAULT_CURRENCY: str = "USD"
    MAX_ORDER_VALUE_LIMIT: Decimal = Decimal("500000.00")
    MAX_PORTFOLIO_LEVERAGE: Decimal = Decimal("2.0")
    ALLOW_MARGIN_TRADING: bool = False

    @property
    def async_database_url(self) -> str:
        """Constructs an asyncpg connection string."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        """Constructs a Redis connection URL."""
        auth_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key_entropy(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long for cryptographic safety.")
        return v


settings = Settings()