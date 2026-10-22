"""Order lifecycle: creation, validation, status transitions, assignment, serialization."""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Order, OrderItem, OrderNote, OrderStatusHistory, Product, User
from ..security import MANAGERS, OFFICE
from .audit import audit
from .message_parser import ParsedOrder
from .payment_service import paise, payment_detail, payment_summary, refresh_payment_state
from .routing_service import route_order
from .stock_service import release, reserve, ship, stock_flags, stock_level

STATUSES = [
    "New", "Needs Review", "Confirmed", "Assigned", "In Progress",
    "On Hold", "Ready / Dispatched", "Completed", "Cancelled",
]
OPEN_STATUSES = ["New", "Needs Review", "Confirmed", "Assigned", "In Progress", "On Hold"]
CLOSED_STATUSES = ["Completed", "Cancelled"]

TRANSITIONS = {
    "New": ["Needs Review", "Confirmed", "Cancelled"],
    "Needs Review": ["Confirmed", "Cancelled"],
    "Confirmed": ["Assigned", "On Hold", "Cancelled"],
    "Assigned": ["In Progress", "On Hold", "Cancelled"],
    "In Progress": ["Ready / Dispatched", "Completed", "On Hold", "Cancelled"],
    "On Hold": ["Assigned", "In Progress", "Cancelled"],
    "Ready / Dispatched": ["Completed", "On Hold"],
    "Completed": [],
    "Cancelled": [],
}
DEPARTMENT_STATUSES = {"In Progress", "On Hold", "Ready / Dispatched", "Completed"}
REASON_REQUIRED = {"On Hold", "Cancelled"}


# ---------------------------------------------------------------- permissions

def can_view(user: User, order: Order) -> bool:
    return user.role in OFFICE or order.department_id == user.department_id


def ensure_can_view(user: User, order: Order) -> None:
    if not can_view(user, order):
        raise HTTPException(403, "This order belongs to another department")


def allowed_transitions(user: User, order: Order) -> list[str]:
    targets = TRANSITIONS.get(order.status, [])
    if user.role in MANAGERS:
        return targets
    if user.role == "operator":
        return [t for t in targets if t not in {"Ready / Dispatched", "Completed"}]
    if order.department_id != user.department_id:
        return []
    return [t for t in targets if t in DEPARTMENT_STATUSES]


def can_edit_details(user: User, order: Order) -> bool:
    return user.role in OFFICE and order.status not in CLOSED_STATUSES


# ---------------------------------------------------------------- validation

def validate_order(order: Order) -> list[dict]:
    flags = []
    if not (order.customer_name or "").strip():
        flags.append({"field": "customer_name", "message": "Customer name is required."})
    if not (order.delivery_address or "").strip():
        flags.append({"field": "delivery_address", "message": "Delivery location is required."})
    if not order.requested_date:
        flags.append({"field": "requested_date", "message": "Requested date is required."})
    if not order.items:
        flags.append({"field": "items", "message": "At least one item is required."})
    for item in order.items:
        if item.product_id is None:
            flags.append({"field": "items", "message": f"\"{item.product_name}\" is not linked to a catalogue product."})
        if item.quantity is None or item.quantity <= 0:
            flags.append({"field": "items", "message": f"Quantity missing for {item.product_name}."})
    return flags


def review_problems(db: Session, order: Order) -> list[dict]:
    """Missing details plus stock shortages - anything that blocks confirmation."""
    return validate_order(order) + stock_flags(db, order)


def refresh_review_state(db: Session, order: Order, user: User | None) -> None:
    """Recompute review flags after a manual edit and move between New / Needs Review."""
    order.review_flags = review_problems(db, order)
    if order.status in ("New", "Needs Review"):
        target = "Needs Review" if order.review_flags else "New"
        if target != order.status:
            record_status(db, order, target, user, "Review flags recalculated after edit")


# ---------------------------------------------------------------- creation

def record_status(db: Session, order: Order, new_status: str, user: User | None, comment: str | None) -> None:
    order.history.append(OrderStatusHistory(
        old_status=order.status if order.id else None,
        new_status=new_status,
        changed_by=user.id if user else None,
        comment=comment,
    ))
    order.status = new_status


def _assign_number(db: Session, order: Order) -> None:
    db.flush()
    today = get_settings().business_now()
    order.order_number = f"ORD-{today:%Y%m%d}-{order.id:04d}"


def create_order_from_parsed(db: Session, parsed: ParsedOrder, user: User | None, source_note: str) -> Order:
    order = Order(
        order_number=f"TMP-{id(parsed)}",
        customer_name=parsed.customer_name,
        contact_reference=parsed.contact_reference,
        delivery_address=parsed.delivery_address,
        requested_date=parsed.requested_date,
        notes="\n".join(parsed.notes) or None,
        extraction_method=parsed.method,
        created_by=user.id if user else None,
        status="New",
        stock_state="none",
    )
    for item in parsed.items:
        product = db.get(Product, item.product_id) if item.product_id else None
        order.items.append(OrderItem(
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=Decimal(str(item.quantity)) if item.quantity is not None else None,
            unit=item.unit,
            unit_price=product.unit_price if product else None,
        ))
    sync_amount_from_items(order)
    order.review_flags = parsed.flags + stock_flags(db, order)
    db.add(order)
    initial = "Needs Review" if order.review_flags else "New"
    order.history.append(OrderStatusHistory(new_status=initial, changed_by=user.id if user else None, comment=source_note))
    order.status = initial
    _assign_number(db, order)
    audit(db, user, "order_created", "order", order.id, f"{order.order_number} via {parsed.method} extraction")
    return order


def apply_items(db: Session, order: Order, items: list) -> None:
    order.items.clear()
    for item in items:
        product = db.get(Product, item.product_id) if item.product_id else None
        order.items.append(OrderItem(
            product_id=product.id if product else None,
            product_name=product.product_name if product else item.product_name,
            quantity=item.quantity,
            unit=item.unit or (product.unit if product else None),
            unit_price=paise(item.unit_price) if item.unit_price is not None else (product.unit_price if product else None),
            item_notes=item.item_notes,
        ))
    sync_amount_from_items(order)


def items_total(order: Order) -> Decimal | None:
    """Sum of the item lines, or None while any line is missing a price or quantity."""
    if not order.items or any(i.line_total is None for i in order.items):
        return None
    return sum((i.line_total for i in order.items), Decimal("0.00"))


def sync_amount_from_items(order: Order) -> None:
    """Fill the order amount from the item prices. Left alone when some item has no price,
    so an amount typed in by hand is kept."""
    total = items_total(order)
    if total is not None:
        order.amount_due = total
    refresh_payment_state(order)


def create_manual_order(db: Session, data, user: User | None, method: str = "manual",
                        comment: str = "Manual order entry") -> Order:
    order = Order(
        order_number=f"TMP-{method}",
        customer_name=data.customer_name,
        contact_reference=data.contact_reference,
        delivery_address=data.delivery_address,
        requested_date=data.requested_date,
        notes=data.notes,
        extraction_method=method,
        created_by=user.id if user else None,
        stock_state="none",
    )
    db.add(order)
    apply_items(db, order, data.items)
    order.review_flags = review_problems(db, order)
    initial = "Needs Review" if order.review_flags else "New"
    order.history.append(OrderStatusHistory(new_status=initial, changed_by=user.id if user else None, comment=comment))
    order.status = initial
    _assign_number(db, order)
    audit(db, user, "order_created", "order", order.id,
          "Placed by the customer on the online shop" if method == "shop" else f"{order.order_number} entered manually")
    return order


def create_shop_order(db: Session, data) -> Order:
    """An order a customer placed on the public shop page. It goes through review like any other."""
    return create_manual_order(db, data, None, method="shop", comment="Placed by the customer on the online shop")


def update_items(db: Session, order: Order, items: list, user: User) -> None:
    """Replace the items. If the order already holds stock, swap the reservation (or refuse)."""
    held = order.stock_state == "reserved"
    if held:
        release(db, order, user, "Items edited")
    apply_items(db, order, items)
    db.flush()
    if held:
        reserve(db, order, user)  # raises 422 when the new quantities are not in stock


# ---------------------------------------------------------------- lifecycle

def confirm_and_route(db: Session, order: Order, user: User, comment: str | None) -> str:
    if order.status not in ("New", "Needs Review"):
        raise HTTPException(400, f"Only New or Needs Review orders can be confirmed (current: {order.status})")
    problems = review_problems(db, order)
    if problems:
        order.review_flags = problems
        if order.status == "New":
            record_status(db, order, "Needs Review", user, "Cannot confirm: " + problems[0]["message"])
        raise HTTPException(422, {"message": "Order cannot be confirmed yet", "flags": problems})
    reserve(db, order, user)
    order.review_flags = []
    record_status(db, order, "Confirmed", user, comment or "Details checked by operator")
    source_text = " ".join(m.message_text for m in order.messages)
    decision = route_order(db, order, source_text)
    if decision.department_id:
        order.department_id = decision.department_id
        record_status(db, order, "Assigned", user, decision.reason)
    audit(db, user, "order_confirmed", "order", order.id, decision.reason)
    return decision.reason


def change_status(db: Session, order: Order, new_status: str, user: User, comment: str | None) -> None:
    if new_status not in STATUSES:
        raise HTTPException(400, f"Unknown status {new_status}")
    if new_status == "Confirmed":
        confirm_and_route(db, order, user, comment)
        return
    if new_status not in allowed_transitions(user, order):
        raise HTTPException(400, f"Cannot move order from {order.status} to {new_status}")
    if new_status in REASON_REQUIRED and not (comment or "").strip():
        raise HTTPException(422, f"A reason is required to put an order {new_status}")
    if new_status == "Assigned" and not order.department_id:
        raise HTTPException(422, "Choose a department before assigning")
    old = order.status
    if new_status == "Cancelled":
        release(db, order, user, "Order cancelled")
    elif new_status in ("Ready / Dispatched", "Completed"):
        ship(db, order, user)
    record_status(db, order, new_status, user, comment)
    audit(db, user, "status_changed", "order", order.id, f"{old} -> {new_status}")


def assign(db: Session, order: Order, department_id: int, assigned_user_id: int | None, user: User, comment: str | None) -> None:
    if order.status in ("New", "Needs Review"):
        raise HTTPException(400, "Confirm the order before assigning it")
    if order.status in CLOSED_STATUSES:
        raise HTTPException(400, "Closed orders cannot be reassigned")
    if assigned_user_id:
        assignee = db.get(User, assigned_user_id)
        if assignee is None or (assignee.department_id not in (None, department_id)):
            raise HTTPException(422, "Assigned user must belong to the selected department")
    changed = order.department_id != department_id or order.assigned_user_id != assigned_user_id
    order.department_id = department_id
    order.assigned_user_id = assigned_user_id
    db.flush()
    db.refresh(order, ["department", "assigned_user"])
    target = order.department.department_name if order.department else "?"
    if order.assigned_user:
        target += f" / {order.assigned_user.display_name}"
    if order.status == "Confirmed":
        record_status(db, order, "Assigned", user, comment or f"Assigned to {target}")
    elif changed:
        order.history.append(OrderStatusHistory(
            old_status=order.status, new_status=order.status, changed_by=user.id,
            comment=(comment + " - " if comment else "") + f"Reassigned to {target}",
        ))
    audit(db, user, "order_assigned", "order", order.id, target)


def add_note(db: Session, order: Order, user: User, note: str) -> None:
    order.order_notes.append(OrderNote(user_id=user.id, note=note.strip()))
    audit(db, user, "note_added", "order", order.id, note[:200])


def get_order_or_404(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


# ---------------------------------------------------------------- serialization

def is_delayed(order: Order, today: date) -> bool:
    return bool(order.requested_date and order.requested_date < today
                and order.status not in ("Completed", "Cancelled", "Ready / Dispatched"))


def _num(value: Decimal | None):
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def order_summary(order: Order, today: date) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "delivery_address": order.delivery_address,
        "requested_date": order.requested_date,
        "status": order.status,
        "department_id": order.department_id,
        "department_name": order.department.department_name if order.department else None,
        "assigned_user_name": order.assigned_user.display_name if order.assigned_user else None,
        "items_preview": ", ".join(
            f"{_num(i.quantity) if i.quantity is not None else '?'} {i.unit or ''} {i.product_name}".replace("  ", " ")
            for i in order.items
        ),
        "item_count": len(order.items),
        "flag_count": len(order.review_flags or []),
        "extraction_method": order.extraction_method,
        "is_delayed": is_delayed(order, today),
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        **payment_summary(order),
    }


def order_detail(order: Order, user: User, today: date) -> dict:
    data = order_summary(order, today)
    data.update({
        "contact_reference": order.contact_reference,
        "notes": order.notes,
        "assigned_user_id": order.assigned_user_id,
        "created_by_name": order.creator.display_name if order.creator else None,
        "review_flags": order.review_flags or [],
        "items": [{
            "id": i.id, "product_id": i.product_id,
            "product_code": i.product.product_code if i.product else None,
            "product_name": i.product_name, "quantity": _num(i.quantity), "unit": i.unit,
            "unit_price": float(i.unit_price) if i.unit_price is not None else None,
            "line_total": float(i.line_total) if i.line_total is not None else None,
            "item_notes": i.item_notes,
            "available": _num(i.product.available) if i.product else None,
            "stock_level": stock_level(i.product) if i.product else None,
        } for i in order.items],
        "stock_state": order.stock_state,
        "items_total": float(t) if (t := items_total(order)) is not None else None,
        "history": [{
            "old_status": h.old_status, "new_status": h.new_status, "changed_at": h.changed_at,
            "changed_by": h.user.display_name if h.user else "System", "comment": h.comment,
        } for h in order.history],
        "internal_notes": [{
            "id": n.id, "note": n.note, "created_at": n.created_at,
            "user": n.user.display_name if n.user else "System",
        } for n in order.order_notes],
        "messages": [{
            "id": m.id, "source": m.source, "sender_name": m.sender_name,
            "sender_reference": m.sender_reference, "message_text": m.message_text,
            "received_at": m.received_at,
        } for m in order.messages],
        "allowed_transitions": allowed_transitions(user, order),
        "can_edit": can_edit_details(user, order),
        "can_confirm": user.role in OFFICE and order.status in ("New", "Needs Review"),
        "can_assign": user.role in OFFICE and order.status not in ("New", "Needs Review", *CLOSED_STATUSES),
        **payment_detail(order, user),
    })
    return data


def list_query(user: User):
    query = select(Order)
    if user.role == "department":
        query = query.where(Order.department_id == user.department_id)
    return query
