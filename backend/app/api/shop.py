"""Public online shop: no login. Customers browse the catalogue, place an order and track it.

Only stock *levels* (ok / low / out) are shown, never quantities. Prices are shown; the
customer never sets a price - order lines always take the catalogue price. Orders land in the review
queue exactly like WhatsApp orders - nothing is reserved until an operator confirms.
"""
import re
import time
from collections import defaultdict, deque
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Branch, Order, Product
from ..schemas import OrderCreate, OrderItemIn, ShopOrderIn
from ..services import order_service as svc
from ..services.stock_service import stock_level

router = APIRouter(prefix="/api/public", tags=["public shop"])

ORDER_LIMIT = 10            # orders per IP ...
ORDER_WINDOW = 10 * 60      # ... per 10 minutes
_recent: dict[str, deque] = defaultdict(deque)

CUSTOMER_STATUS = {
    "New": "Received", "Needs Review": "Received - being checked", "Confirmed": "Confirmed",
    "Assigned": "Confirmed", "In Progress": "Being prepared", "On Hold": "On hold",
    "Ready / Dispatched": "Dispatched", "Completed": "Delivered", "Cancelled": "Cancelled",
}


def rate_limit(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _recent[key]
    while hits and now - hits[0] > ORDER_WINDOW:
        hits.popleft()
    if len(hits) >= ORDER_LIMIT:
        raise HTTPException(429, "Too many orders from this device. Please try again in a few minutes.")
    hits.append(now)


def digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


@router.get("/catalogue")
def catalogue(db: Session = Depends(get_db)):
    products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.product_name)).all()
    branches = db.scalars(select(Branch).where(Branch.active.is_(True)).order_by(Branch.branch_name)).all()
    return {
        "products": [{
            "id": p.id, "product_code": p.product_code, "product_name": p.product_name,
            "unit": p.unit, "description": p.description,
            "category": p.department.department_name if p.department else "Other",
            "stock_level": stock_level(p),
            "unit_price": float(p.unit_price) if p.unit_price is not None else None,
        } for p in products],
        "branches": [{"id": b.id, "branch_name": b.branch_name, "address": b.address} for b in branches],
    }


@router.post("/orders", status_code=201)
def place_order(body: ShopOrderIn, request: Request, db: Session = Depends(get_db)):
    if body.website:
        raise HTTPException(422, "Invalid request")
    if body.requested_date < get_settings().business_now().date():
        raise HTTPException(422, "Requested date cannot be in the past")

    address = (body.delivery_address or "").strip()
    if body.branch_id:
        branch = db.get(Branch, body.branch_id)
        if branch is None or not branch.active:
            raise HTTPException(422, "Unknown branch")
        address = branch.address or branch.branch_name
    if not address:
        raise HTTPException(422, "Choose a branch or enter a delivery address")

    quantities: dict[int, Decimal] = {}
    for item in body.items:
        quantities[item.product_id] = quantities.get(item.product_id, Decimal(0)) + item.quantity
    items = []
    for product_id, qty in quantities.items():
        product = db.get(Product, product_id)
        if product is None or not product.active:
            raise HTTPException(422, "One of the products is no longer available")
        items.append(OrderItemIn(product_id=product.id, product_name=product.product_name,
                                 quantity=qty, unit=product.unit))

    rate_limit(request)
    data = OrderCreate(
        customer_name=body.customer_name.strip(), contact_reference=body.phone.strip(),
        delivery_address=address, requested_date=body.requested_date,
        notes=(body.notes or "").strip() or None, items=items,
    )
    order = svc.create_shop_order(db, data)
    db.commit()
    return {"order_number": order.order_number, "status": CUSTOMER_STATUS[order.status],
            "message": "Thank you! Your order has been received. Our team will confirm it shortly."}


@router.get("/orders/{order_number}")
def track_order(order_number: str, phone: str, db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.order_number == order_number.strip().upper()))
    # Same answer for "no such order" and "wrong phone" so order numbers can't be probed.
    if order is None or not digits(phone) or digits(phone) != digits(order.contact_reference):
        raise HTTPException(404, "No order found with that number and phone")
    timeline, last = [], None
    for h in order.history:
        label = CUSTOMER_STATUS.get(h.new_status, h.new_status)
        if label != last:
            timeline.append({"status": label, "at": h.changed_at})
            last = label
    return {
        "order_number": order.order_number,
        "status": CUSTOMER_STATUS.get(order.status, order.status),
        "customer_name": order.customer_name,
        "delivery_address": order.delivery_address,
        "requested_date": order.requested_date,
        "placed_at": order.created_at,
        "items": [{"product_name": i.product_name, "quantity": float(i.quantity or 0), "unit": i.unit,
                   "unit_price": float(i.unit_price) if i.unit_price is not None else None,
                   "line_total": float(i.line_total) if i.line_total is not None else None}
                  for i in order.items],
        "amount_due": float(order.amount_due) if order.amount_due is not None else None,
        "amount_paid": float(order.amount_paid or 0),
        "payment_status": order.payment_status,
        "timeline": timeline,
    }
