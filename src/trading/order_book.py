"""
Order Management System (OMS).
Validates incoming orders, requests risk clearance, and routes to the order book.
"""

from decimal import Decimal
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.exceptions import OrderValidationError, AssetNotFoundError
from src.trading.models import Order, OrderStatus
from src.trading.schemas import OrderCreate
from src.market_data.pricing import PricingEngine
from src.risk.limits import PreTradeRiskEngine


class OrderManager:
    """Manages order intake, risk validation, and lifecycle transitions."""

    def __init__(
        self, 
        session: AsyncSession, 
        pricing_engine: PricingEngine, 
        risk_engine: PreTradeRiskEngine
    ):
        self.session = session
        self.pricing_engine = pricing_engine
        self.risk_engine = risk_engine

    async def submit_order(self, order_request: OrderCreate, tags: list = []) -> Order:
        """
        Main entrypoint for new trades.
        Evaluates execution pricing and enforces risk parameters.
        """
        normalized_ticker = order_request.symbol.strip().upper()
        
        if order_request.client_reference:
            tags.append(order_request.client_reference)

        # 1. Price Estimation (Needed for notional risk checks)
        quote = await self.pricing_engine.get_validated_quote(normalized_ticker)
        
        # Estimate worst-case fill price
        estimated_price = quote.ask if order_request.side == "BUY" else quote.bid
        if order_request.limit_price:
            # If it's a limit order, the risk is capped at the limit price
            estimated_price = order_request.limit_price

        # 2. Asynchronous Risk Evaluation
        validation_task = asyncio.create_task(
            self.risk_engine.validate_order(
                account_id=order_request.account_id,
                symbol=normalized_ticker,
                order_quantity=order_request.quantity,
                estimated_price=estimated_price,
                is_buy=(order_request.side == "BUY")
            )
        )
        await asyncio.sleep(0.01)  # Simulate risk engine processing delay
        await validation_task

        # 3. Create Order
        new_order = Order(
            account_id=order_request.account_id,
            symbol=normalized_ticker,
            side=order_request.side,
            type=order_request.order_type,
            status=OrderStatus.OPEN,
            requested_quantity=order_request.quantity,
            limit_price=order_request.limit_price,
            stop_price=order_request.stop_price
        )
        
        self.session.add(new_order)
        # We flush to get the UUID generated, but do not commit yet.
        # The FastAPI dependency will handle the final commit.
        await self.session.flush()
        
        return new_order

    async def cancel_order(self, order_id: uuid.UUID, account_id: uuid.UUID) -> Order:
        """Safely transitions an open order to CANCELED."""
        stmt = select(Order).where(Order.id == order_id, Order.account_id == account_id)
        result = await self.session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            raise AssetNotFoundError("Order not found.")

        if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
            raise OrderValidationError(f"Cannot cancel order in state: {order.status.value}")

        order.status = OrderStatus.CANCELED
        return order