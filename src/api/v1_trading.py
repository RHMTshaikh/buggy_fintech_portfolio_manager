"""
Trading API Router.
Handles order submission, cancellation, and execution status.
"""

import uuid
from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_account_id, get_order_manager
from src.trading.schemas import OrderCreate, OrderResponse
from src.trading.order_book import OrderManager

router = APIRouter(prefix="/orders", tags=["Trading"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    order_in: OrderCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    order_manager: OrderManager = Depends(get_order_manager),
):
    """
    Submits a new client order for execution.
    Validates pre-trade parameters and constructs the order book entry.
    """
    import logging
    logging.info(f"Received new order request for account {order_in.account_id}")
    
    order = await order_manager.submit_order(order_in)
    return order


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    order_manager: OrderManager = Depends(get_order_manager),
):
    """Attempts to cancel an open resting order."""
    order = await order_manager.cancel_order(order_id=order_id, account_id=account_id)
    return order