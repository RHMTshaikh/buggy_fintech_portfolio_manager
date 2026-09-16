"""
Market Data & Order Execution Synchronization.
Sweeps the order book and attempts fills against live market quotes.
"""

from celery import shared_task
from sqlalchemy import select

from src.core.database import AsyncSessionFactory
from src.trading.models import Order, OrderStatus
from src.trading.execution import ExecutionEngine
from src.market_data.pricing import PricingEngine
from src.portfolio.ledger import LedgerService
from tasks.worker import run_async


async def _execute_open_orders_async() -> int:
    """Async core logic for processing open resting orders."""
    filled_count = 0
    
    # Task-scoped DB session lifecycle
    async with AsyncSessionFactory() as session:
        try:
            # Initialize bounded contexts for this task
            pricing_engine = PricingEngine()
            ledger_service = LedgerService(session)
            execution_engine = ExecutionEngine(session, pricing_engine, ledger_service)

            # Query all executable orders
            stmt = select(Order.id).where(
                Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED])
            )
            result = await session.execute(stmt)
            open_order_ids = result.scalars().all()

            for order_id in open_order_ids:
                try:
                    # Attempt execution (will return None if limit price isn't met)
                    # FIX: Use a nested transaction (savepoint) to prevent session taint
                    async with session.begin_nested():
                        execution = await execution_engine.attempt_execution(order_id)
                        if execution:
                            filled_count += 1
                except Exception as e:
                    # Isolate failures to the specific order, don't crash the whole batch
                    print(f"Failed to execute order {order_id}: {str(e)}")
                    # Note: Do NOT rollback the whole session here, we will handle commit per-batch 
                    # or rely on the execution engine's internal atomic handling if refactored.
                    # For total safety, we should commit per order.
                    # The begin_nested() block automatically rolls back to the savepoint
                    # upon exception. The parent session remains perfectly healthy!
            
            # Commit all successful executions
            await session.commit()
            return filled_count

        except Exception:
            await session.rollback()
            raise


@shared_task(name="tasks.sweep_order_book", bind=True, max_retries=3)
@run_async
async def sweep_order_book(self: Any) -> dict[str, int]:
    """
    Celery task entrypoint.
    Typically scheduled to run every 1-5 seconds during market hours.
    """
    filled_count = await _execute_open_orders_async()
    return {"status": "success", "orders_filled": filled_count}