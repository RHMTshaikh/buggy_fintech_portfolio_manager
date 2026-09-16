"""
Execution Management System (EMS).
Simulates market routing and binds trade execution to atomic ledger settlement.
"""

import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from src.core.exceptions import OrderValidationError
from src.trading.models import Order, OrderStatus, TradeExecution
from src.market_data.pricing import PricingEngine
from src.portfolio.ledger import LedgerService


class ExecutionEngine:
    """
    Handles the physical execution of orders against the market and ensures
    that executions strictly result in balanced ledger movements.
    """

    def __init__(
        self, 
        session: AsyncSession, 
        pricing_engine: PricingEngine,
        ledger_service: LedgerService
        ):
        self.session = session
        self.pricing_engine = pricing_engine
        self.ledger_service = ledger_service

    async def attempt_execution(self, order_id: uuid.UUID) -> TradeExecution | None:
        """
        Attempts to fill an open order, utilizing automatic retries for optimistic lock failures.
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Wrap the entire execution attempt in a savepoint
                async with self.session.begin_nested():
                    stmt = select(Order).where(Order.id == order_id)
                    result = await self.session.execute(stmt)
                    order = result.scalar_one_or_none()

                    if not order:
                        raise ValueError(f"Order {order_id} not found.")

                    if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
                        raise OrderValidationError(f"Order {order_id} is not in an executable state.")

                    # 1. Retrieve current market reality
                    quote = await self.pricing_engine.get_validated_quote(order.symbol)

                    # 2. Matchmaking Logic
                    fill_price: Decimal | None = None
                    if order.type == "MARKET":
                        fill_price = quote.ask if order.side == "BUY" else quote.bid
                    elif order.type == "LIMIT":
                        if order.side == "BUY" and quote.ask <= order.limit_price:
                            fill_price = quote.ask
                        elif order.side == "SELL" and quote.bid >= order.limit_price:
                            fill_price = quote.bid

                    if not fill_price:
                        return None  # Cannot be filled at current market conditions

                    # 3. Execution Simulation
                    remaining_qty = order.requested_quantity - order.filled_quantity
                    executed_qty = remaining_qty 
                    broker_ref = f"EXEC-{uuid.uuid4().hex[:8].upper()}"

                    execution = TradeExecution(
                        order_id=order.id,
                        execution_price=fill_price,
                        quantity=executed_qty,
                        broker_reference_id=broker_ref
                    )
                    self.session.add(execution)

                    # 4. State Update
                    order.filled_quantity += executed_qty
                    if order.filled_quantity >= order.requested_quantity:
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.PARTIALLY_FILLED

                    # 5. ATOMIC LEDGER SETTLEMENT
                    await self.ledger_service.process_trade_settlement(
                        account_id=order.account_id,
                        symbol=order.symbol,
                        quantity=executed_qty,
                        execution_price=fill_price,
                        is_buy=(order.side == "BUY"),
                        reference_id=broker_ref
                    )

                    return execution

            except StaleDataError:
                if attempt == max_retries - 1:
                    print(f"Execution failed for order {order_id} after {max_retries} concurrent lock conflicts.")
                    raise
                # The savepoint rolled back. The loop continues, automatically fetching fresh data.