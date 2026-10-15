"""Stock: levels, shortage flags, and the reserve -> dispatch / release lifecycle of an order.

Available = on hand - reserved.  Confirming an order reserves its quantities, cancelling releases
them, and dispatching (or completing without a dispatch step) takes them out of on-hand.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Order, Product, StockMovement, User
from ..security import MANAGERS


def fmt(value: Decimal | float | int | None) -> str:
    if value is None:
        return "0"
    value = Decimal(str(value))
    return str(int(value)) if value == value.to_integral_value() else f"{value.normalize()}"


def level_for(available: Decimal, reorder_level: Decimal) -> str:
    """ok | low | out - the only thing the public shop is told about stock."""
    if available <= 0:
        return "out"
    if available <= reorder_level:
        return "low"
    return "ok"


def stock_level(product: Product) -> str:
    return level_for(product.available, product.reorder_level or Decimal(0))


def demand_of(order: Order) -> dict[int, Decimal]:
    """Total quantity per catalogue product (the same product can appear on two lines)."""
    demand: dict[int, Decimal] = {}
    for item in order.items:
        if item.product_id and item.quantity and item.quantity > 0:
            demand[item.product_id] = demand.get(item.product_id, Decimal(0)) + Decimal(str(item.quantity))
    return demand


def shortage_flags(demand: dict[int, Decimal], products: dict[int, Product]) -> list[dict]:
    flags = []
    for product_id, qty in demand.items():
        product = products.get(product_id)
        if product is None:
            continue
        available = product.available
        if qty > available:
            unit = product.unit or ""
            if available <= 0:
                message = f"{product.product_name} is out of stock (ordered {fmt(qty)} {unit})."
            else:
                message = (f"Only {fmt(available)} {unit} of {product.product_name} in stock "
                           f"(ordered {fmt(qty)}).")
            flags.append({"field": "stock", "message": message.replace("  ", " ")})
    return flags


def stock_flags(db: Session, order: Order) -> list[dict]:
    """Shortages for an order that does not hold stock yet (New / Needs Review)."""
    if order.stock_state != "none" and order.stock_state is not None:
        return []
    demand = demand_of(order)
    products = {pid: db.get(Product, pid) for pid in demand}
    return shortage_flags(demand, products)


def _lock(db: Session, product_ids) -> dict[int, Product]:
    rows = db.scalars(
        select(Product).where(Product.id.in_(list(product_ids)))
        .with_for_update().execution_options(populate_existing=True)
    ).all()
    return {p.id: p for p in rows}


def _move(db: Session, product: Product, kind: str, qty: Decimal, user: User | None,
          reason: str | None, order: Order | None = None) -> None:
    db.add(StockMovement(
        product_id=product.id, movement_type=kind, quantity=qty,
        on_hand_after=product.stock_on_hand, reserved_after=product.stock_reserved,
        order_id=order.id if order else None, user_id=user.id if user else None, reason=reason,
    ))


def reserve(db: Session, order: Order, user: User | None) -> None:
    if order.stock_state != "none":
        return
    demand = demand_of(order)
    products = _lock(db, demand)
    problems = shortage_flags(demand, products)
    if problems:
        raise HTTPException(422, {"message": "Not enough stock to confirm this order", "flags": problems})
    for product_id, qty in demand.items():
        product = products[product_id]
        product.stock_reserved = (product.stock_reserved or 0) + qty
        _move(db, product, "reserve", qty, user, f"Reserved for {order.order_number}", order)
    order.stock_state = "reserved"


def release(db: Session, order: Order, user: User | None, reason: str) -> None:
    if order.stock_state != "reserved":
        return
    demand = demand_of(order)
    products = _lock(db, demand)
    for product_id, qty in demand.items():
        product = products[product_id]
        product.stock_reserved = max(Decimal(0), (product.stock_reserved or 0) - qty)
        _move(db, product, "release", -qty, user, f"{reason} ({order.order_number})", order)
    order.stock_state = "none"


def ship(db: Session, order: Order, user: User | None) -> None:
    if order.stock_state != "reserved":
        return  # orders confirmed before stock tracking existed hold nothing
    demand = demand_of(order)
    products = _lock(db, demand)
    for product_id, qty in demand.items():
        product = products[product_id]
        product.stock_reserved = max(Decimal(0), (product.stock_reserved or 0) - qty)
        product.stock_on_hand = max(Decimal(0), (product.stock_on_hand or 0) - qty)
        _move(db, product, "dispatch", -qty, user, f"Dispatched {order.order_number}", order)
    order.stock_state = "shipped"


# ---------------------------------------------------------------- manual stock changes

def can_manage_stock(user: User, product: Product) -> bool:
    return user.role in MANAGERS or (
        user.role == "department" and product.department_id is not None
        and product.department_id == user.department_id
    )


def receive(db: Session, product: Product, qty: Decimal, user: User, reason: str | None) -> None:
    if qty <= 0:
        raise HTTPException(422, "Quantity received must be more than zero")
    product = _lock(db, [product.id])[product.id]
    product.stock_on_hand = (product.stock_on_hand or 0) + qty
    _move(db, product, "in", qty, user, (reason or "").strip() or "Stock received")


def adjust(db: Session, product: Product, delta: Decimal, user: User, reason: str) -> None:
    if delta == 0:
        raise HTTPException(422, "Adjustment cannot be zero")
    if not (reason or "").strip():
        raise HTTPException(422, "A reason is required for a stock adjustment")
    product = _lock(db, [product.id])[product.id]
    new_on_hand = (product.stock_on_hand or 0) + delta
    if new_on_hand < (product.stock_reserved or 0):
        raise HTTPException(422, f"On hand cannot go below the {fmt(product.stock_reserved)} "
                                 f"{product.unit} reserved by confirmed orders")
    product.stock_on_hand = new_on_hand
    _move(db, product, "adjust", delta, user, reason.strip())
