"""
Domain-Specific Exception Hierarchy.
Enforces business rule boundaries, invariant violations, and audit details.
"""

from typing import Any


class FintechBaseException(Exception):
    """Base domain exception for all errors originating within the platform."""
    default_message: str = "An unexpected financial domain error occurred."
    default_error_code: str = "INTERNAL_DOMAIN_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.error_code = error_code or self.default_error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serializes the exception for standardized API error responses."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


# ---------------------------------------------------------------------------
# Authentication & Authorization Exceptions
# ---------------------------------------------------------------------------

class AuthenticationFailedError(FintechBaseException):
    default_message = "Authentication failed or token invalid."
    default_error_code = "AUTH_FAILED"
    status_code = 401


class InvalidTokenError(FintechBaseException):
    default_message = "Token format, signature, or claims are invalid."
    default_error_code = "INVALID_TOKEN"
    status_code = 401


class UnauthorizedAccountAccessError(FintechBaseException):
    default_message = "Identity does not possess permissions to manage this account."
    default_error_code = "ACCOUNT_FORBIDDEN"
    status_code = 403


# ---------------------------------------------------------------------------
# Accounting & Ledger Invariant Violations
# ---------------------------------------------------------------------------

class InsufficientFundsError(FintechBaseException):
    """Raised when available cash balance cannot satisfy debit transaction."""
    default_message = "Available cash balance is insufficient to execute transaction."
    default_error_code = "INSUFFICIENT_FUNDS"
    status_code = 400


class DoubleEntryLedgerMismatchError(FintechBaseException):
    """
    CRITICAL INVARIANT VIOLATION:
    Raised when debits do not strictly balance credits in an accounting journal.
    """
    default_message = "Accounting journal entry is unbalanced: Debits do not equal Credits."
    default_error_code = "LEDGER_UNBALANCED"
    status_code = 500


# ---------------------------------------------------------------------------
# Trading & Execution Exceptions
# ---------------------------------------------------------------------------

class OrderValidationError(FintechBaseException):
    default_message = "Order parameters failed validation constraints."
    default_error_code = "ORDER_VALIDATION_FAILED"
    status_code = 422


class OrderNotFoundError(FintechBaseException):
    default_message = "Requested order record does not exist."
    default_error_code = "ORDER_NOT_FOUND"
    status_code = 404


class InsufficientPositionQuantityError(FintechBaseException):
    """Raised when an order attempts to sell more shares/contracts than owned."""
    default_message = "Cannot execute sell order: Position quantity insufficient."
    default_error_code = "INSUFFICIENT_POSITION"
    status_code = 400


class MarketClosedError(FintechBaseException):
    default_message = "Order rejected: Target exchange market is currently closed."
    default_error_code = "MARKET_CLOSED"
    status_code = 400


# ---------------------------------------------------------------------------
# Risk & Compliance Failures
# ---------------------------------------------------------------------------

class RiskLimitExceededError(FintechBaseException):
    default_message = "Pre-trade risk checks failed: Portfolio concentration or exposure exceeded."
    default_error_code = "RISK_LIMIT_BREACH"
    status_code = 403


class PatternDayTradingViolationError(FintechBaseException):
    default_message = "Account violates FINRA Rule 4210 pattern day trading restrictions."
    default_error_code = "PDT_RESTRICTION"
    status_code = 403


# ---------------------------------------------------------------------------
# Market Data & Pricing Exceptions
# ---------------------------------------------------------------------------

class StaleMarketDataError(FintechBaseException):
    """Raised when tick/quote timestamp exceeds freshness tolerance threshold."""
    default_message = "Price quote rejected: Market data feed is stale."
    default_error_code = "STALE_MARKET_DATA"
    status_code = 503


class AssetNotFoundError(FintechBaseException):
    default_message = "Target ticker symbol or financial instrument not found."
    default_error_code = "ASSET_NOT_FOUND"
    status_code = 404