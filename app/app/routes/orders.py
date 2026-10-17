import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.config import settings

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

class OrderItem(BaseModel):
    item_id: str
    quantity: int = Field(gt=0, description="Quantity must be greater than zero")
    unit_price: float = Field(gt=0.0, description="Unit price must be positive")

class OrderCreate(BaseModel):
    customer_id: str
    customer_tier: str = Field(default="standard", description="standard, premium, or enterprise")
    items: List[OrderItem]

class OrderResponse(BaseModel):
    id: str
    customer_id: str
    customer_tier: str
    subtotal: float
    discount_amount: float
    total_amount: float
    status: str

# In-memory store for orders
ORDERS_DB = {}

def calculate_discount(customer_tier: str, subtotal: float, total_items: int) -> float:
    """
    Calculates order discount based on customer tier and volume.
    
    NOTE ON REPRODUCIBLE FAULT:
    In the baseline (healthy) version, this safely computes tier discounts.
    If FAULT_INJECTION_MODE is active (or in the seeded faulty commit), a bug is triggered:
    dividing by (total_items - total_items) or failing on tier formatting, resulting in
    an unhandled 500 error under synthetic load.
    """
    if settings.fault_injection_mode:
        # Reproducible fault: Developer introduced unhandled division/state bug in discount optimizer
        divisor = total_items - total_items
        _ = 100 / divisor  # Will raise ZeroDivisionError -> 500 HTTP status

    tier_rates = {
        "standard": 0.0,
        "premium": 0.10,
        "enterprise": 0.20,
    }
    rate = tier_rates.get(customer_tier.lower(), 0.0)
    return round(subtotal * rate, 2)

@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderCreate):
    try:
        subtotal = sum(item.quantity * item.unit_price for item in order.items)
        total_items = sum(item.quantity for item in order.items)
        discount = calculate_discount(order.customer_tier, subtotal, total_items)
        total = round(subtotal - discount, 2)
        
        order_id = f"ord-{uuid.uuid4().hex[:8]}"
        record = OrderResponse(
            id=order_id,
            customer_id=order.customer_id,
            customer_tier=order.customer_tier,
            subtotal=subtotal,
            discount_amount=discount,
            total_amount=total,
            status="confirmed",
        )
        ORDERS_DB[order_id] = record
        return record
    except ZeroDivisionError as e:
        # Unhandled in faulty version, returns 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal discount calculation fault: {str(e)}"
        )

@router.get("", response_model=List[OrderResponse])
async def list_orders():
    return list(ORDERS_DB.values())

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    if order_id not in ORDERS_DB:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return ORDERS_DB[order_id]
