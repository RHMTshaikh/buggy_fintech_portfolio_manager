"""
FastAPI Application Entrypoint.
Orchestrates lifecycles, routers, and global exception mapping.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.exceptions import FintechBaseException
from src.market_data.cache import close_redis_pool

from src.api.v1_portfolio import router as portfolio_router
from src.api.v1_trading import router as trading_router
from src.api.v1_market import router as market_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.
    Bootstraps resources on startup and cleanly tears them down on exit.
    """
    # Startup: Resources are lazily initialized on first use, but we could pre-warm caches here
    yield
    # Shutdown: Gracefully drain Redis connection pools to prevent orphaned sockets
    await close_redis_pool()


def create_app() -> FastAPI:
    """Factory function yielding the configured FastAPI instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description="Enterprise-grade Fintech Portfolio & Order Management System",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None, 
        redoc_url=None,
    )

    # Cross-Origin Resource Sharing (CORS) Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else ["https://my-fintech-app.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Global Exception Handler
    # -----------------------------------------------------------------------
    @app.exception_handler(FintechBaseException)
    async def fintech_exception_handler(request: Request, exc: FintechBaseException) -> JSONResponse:
        """
        Intercepts internal domain exceptions (e.g., InsufficientFundsError, RiskLimitExceededError)
        and formats them into secure, machine-readable HTTP responses.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    # -----------------------------------------------------------------------
    # Router Registration
    # -----------------------------------------------------------------------
    api_prefix = settings.API_V1_STR
    app.include_router(market_router, prefix=api_prefix)
    app.include_router(portfolio_router, prefix=api_prefix)
    app.include_router(trading_router, prefix=api_prefix)

    @app.get("/health", tags=["System"])
    async def health_check() -> dict[str, str]:
        """Load balancer and Kubernetes readiness probe."""
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


# The ASGI application instance to be served by Uvicorn or Gunicorn
app = create_app()