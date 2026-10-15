from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Department, Order, OrderItem, User
from ..schemas import AssignRequest, ConfirmRequest, NoteIn, OrderCreate, OrderUpdate, StatusChange
from ..security import OFFICE, get_current_user, require_roles
from ..services import order_service as svc
from ..services.audit import audit

router = APIRouter(prefix="/api/orders", tags=["orders"])


def today() -> date:
    return get_settings().business_now().date()


def detail(db: Session, order: Order, user: User) -> dict:
    db.refresh(order)
    return svc.order_detail(order, user, today())


@router.get("")
def list_orders(
    q: str | None = None,
    status: list[str] | None = Query(None),
    department_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    delayed: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = svc.list_query(user)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(
            Order.order_number.ilike(like), Order.customer_name.ilike(like),
            Order.contact_reference.ilike(like), Order.delivery_address.ilike(like),
            Order.id.in_(select(OrderItem.order_id).where(OrderItem.product_name.ilike(like))),
        ))
    if status:
        query = query.where(Order.status.in_(status))
    if department_id:
        query = query.where(Order.department_id == department_id)
    if date_from:
        query = query.where(Order.requested_date >= date_from)
    if date_to:
        query = query.where(Order.requested_date <= date_to)
    if delayed:
        query = query.where(Order.requested_date < today(),
                            Order.status.not_in(["Completed", "Cancelled", "Ready / Dispatched"]))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    t = today()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [svc.order_summary(o, t) for o in rows]}


@router.post("", status_code=201)
def create_order(body: OrderCreate, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    order = svc.create_manual_order(db, body, user)
    db.commit()
    return detail(db, order, user)


@router.get("/statuses")
def statuses():
    return {"statuses": svc.STATUSES, "transitions": svc.TRANSITIONS}


@router.get("/{order_id}")
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    svc.ensure_can_view(user, order)
    return svc.order_detail(order, user, today())


@router.patch("/{order_id}")
def update_order(order_id: int, body: OrderUpdate, user: User = Depends(require_roles(*OFFICE)),
                 db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    if not svc.can_edit_details(user, order):
        raise HTTPException(400, "This order can no longer be edited")
    changes = body.model_dump(exclude_unset=True)
    items = changes.pop("items", None)
    for key, value in changes.items():
        setattr(order, key, value)
    if items is not None:
        svc.update_items(db, order, body.items, user)
    db.flush()
    svc.refresh_review_state(db, order, user)
    audit(db, user, "order_updated", "order", order.id, ", ".join(sorted(body.model_fields_set)))
    db.commit()
    return detail(db, order, user)


@router.post("/{order_id}/confirm")
def confirm_order(order_id: int, body: ConfirmRequest, user: User = Depends(require_roles(*OFFICE)),
                  db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    try:
        reason = svc.confirm_and_route(db, order, user, body.comment)
    except HTTPException:
        db.commit()  # keep refreshed review flags
        raise
    db.commit()
    return {"routing": reason, "order": detail(db, order, user)}


@router.post("/{order_id}/status")
def set_status(order_id: int, body: StatusChange, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    svc.ensure_can_view(user, order)
    if body.status == "Confirmed" and user.role not in OFFICE:
        raise HTTPException(403, "Only office users can confirm orders")
    svc.change_status(db, order, body.status, user, body.comment)
    db.commit()
    return detail(db, order, user)


@router.post("/{order_id}/assign")
def assign_order(order_id: int, body: AssignRequest, user: User = Depends(require_roles(*OFFICE)),
                 db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    if db.get(Department, body.department_id) is None:
        raise HTTPException(422, "Unknown department")
    svc.assign(db, order, body.department_id, body.assigned_user_id, user, body.comment)
    db.commit()
    return detail(db, order, user)


@router.post("/{order_id}/notes", status_code=201)
def add_note(order_id: int, body: NoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    svc.ensure_can_view(user, order)
    svc.add_note(db, order, user, body.note)
    db.commit()
    return detail(db, order, user)
