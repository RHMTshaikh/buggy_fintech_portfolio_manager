"""
Trading API Schemas & Data Validation.
Enforces strict invariants on incoming client requests.
"""

from decimal import Decimal
import uuid
from pydantic import BaseModel, Field, model_validator

from src.trading.models import OrderSide, OrderType, OrderStatus


class OrderCreate(BaseModel):
    """Payload for submitting a new order to the API."""
    account_id: uuid.UUID
    symbol: str = Field(..., min_length=1, max_length=10, description="Asset ticker symbol")
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0, description="Number of shares/contracts to trade")
    
    limit_price: Decimal | None = Field(None, gt=0, description="Required if order_type is LIMIT")
    stop_price: Decimal | None = Field(None, gt=0, description="Required if order_type is STOP")

    @model_validator(mode="after")
    def validate_pricing_requirements(self) -> "OrderCreate":
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price must be provided for LIMIT orders.")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("stop_price must be provided for STOP orders.")
        if self.order_type == OrderType.MARKET and (self.limit_price or self.stop_price):
            raise ValueError("MARKET orders cannot specify limit or stop prices.")
        return self


class OrderResponse(BaseModel):
    """Serialized output of an Order record."""
    id: uuid.UUID
    account_id: uuid.UUID
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    requested_quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    
    model_config = {"from_attributes": True}