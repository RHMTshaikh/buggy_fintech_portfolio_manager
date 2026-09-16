"""
FastAPI Dependency Injection Graph.
Enforces Authentication, Authorization (IDOR protection), and wires domain engines.
"""

import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_db
from src.core.security import decode_token
from src.core.exceptions import AuthenticationFailedError
from src.market_data.pricing import PricingEngine
from src.portfolio.valuation import ValuationEngine
from src.portfolio.rebalance import RebalanceEngine
from src.risk.limits import PreTradeRiskEngine
from src.trading.order_book import OrderManager

# Standard HTTP Bearer scheme for Swagger UI & clients
security_scheme = HTTPBearer()


def get_current_account_id(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> uuid.UUID:
    """
    Validates JWT and extracts the account identity.
    Prevents IDOR by forcing endpoints to use the cryptographically proven ID.
    """
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        account_id_str = payload.get("sub")
        if not account_id_str:
            raise AuthenticationFailedError("Token missing 'sub' claim (Account ID).")
        return uuid.UUID(account_id_str)
    except ValueError:
        raise AuthenticationFailedError("Invalid Account ID format in token.")
    except Exception as e:
        # Let custom domain exceptions bubble up, wrap others
        if isinstance(e, AuthenticationFailedError):
            raise
        raise AuthenticationFailedError(f"Authentication failed: {str(e)}")


# ---------------------------------------------------------------------------
# Domain Engine Factories
# ---------------------------------------------------------------------------

async def get_pricing_engine() -> PricingEngine:
    """Provides stateless PricingEngine. Reuses global Redis connection."""
    return PricingEngine()


async def get_valuation_engine(
    session: AsyncSession = Depends(get_async_db),
    pricing_engine: PricingEngine = Depends(get_pricing_engine),
) -> ValuationEngine:
    return ValuationEngine(session=session, pricing_engine=pricing_engine)


async def get_risk_engine(
    session: AsyncSession = Depends(get_async_db),
    valuation_engine: ValuationEngine = Depends(get_valuation_engine),
) -> PreTradeRiskEngine:
    return PreTradeRiskEngine(session=session, valuation_engine=valuation_engine)


async def get_order_manager(
    session: AsyncSession = Depends(get_async_db),
    pricing_engine: PricingEngine = Depends(get_pricing_engine),
    risk_engine: PreTradeRiskEngine = Depends(get_risk_engine),
) -> OrderManager:
    return OrderManager(
        session=session, 
        pricing_engine=pricing_engine, 
        risk_engine=risk_engine
    )


async def get_rebalance_engine(
    valuation_engine: ValuationEngine = Depends(get_valuation_engine),
) -> RebalanceEngine:
    return RebalanceEngine(valuation_engine=valuation_engine)