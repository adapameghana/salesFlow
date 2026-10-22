from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AuditLog, Department, Message, Order, Product, User
from ..security import MANAGERS, OFFICE, get_current_user, require_roles
from ..services.stock_service import stock_level

router = APIRouter(prefix="/api/reports", tags=["reports"])

NOT_DELAYABLE = ["Completed", "Cancelled", "Ready / Dispatched"]


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    now = settings.business_now()
    today = now.date()
    start_of_day = datetime.combine(today, time.min, tzinfo=settings.business_tz)

    scope = select(Order)
    if user.role == "department":
        scope = scope.where(Order.department_id == user.department_id)
    orders = scope.subquery()

    def count(*conditions) -> int:
        return db.scalar(select(func.count()).select_from(orders).where(*conditions)) or 0

    by_status = dict(db.execute(select(orders.c.status, func.count()).group_by(orders.c.status)).all())
    by_department = [
        {"department": name or "Unassigned", "open": open_count, "total": total}
        for name, open_count, total in db.execute(
            select(Department.department_name,
                   func.count().filter(orders.c.status.not_in(["Completed", "Cancelled"])),
                   func.count())
            .select_from(orders).outerjoin(Department, Department.id == orders.c.department_id)
            .group_by(Department.department_name).order_by(func.count().desc())
        ).all()
    ]

    week_start = start_of_day - timedelta(days=6)
    created_map: dict[str, int] = {}
    for created_at in db.scalars(select(orders.c.created_at).where(orders.c.created_at >= week_start)):
        key = created_at.astimezone(settings.business_tz).date().isoformat()
        created_map[key] = created_map.get(key, 0) + 1
    per_day = [{"date": (today - timedelta(days=i)).isoformat(),
                "count": created_map.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(6, -1, -1)]

    stock_scope = select(Product).where(Product.active.is_(True))
    if user.role == "department":
        stock_scope = stock_scope.where(Product.department_id == user.department_id)
    low_stock = [
        {"id": p.id, "product_code": p.product_code, "product_name": p.product_name, "unit": p.unit,
         "available": float(p.available), "reorder_level": float(p.reorder_level or 0), "level": stock_level(p)}
        for p in db.scalars(stock_scope).all() if stock_level(p) != "ok"
    ]
    low_stock.sort(key=lambda r: (r["level"] != "out", r["available"]))

    return {
        "today": today,
        "total": count(),
        "created_today": count(orders.c.created_at >= start_of_day),
        "needs_review": count(orders.c.status.in_(["New", "Needs Review"])),
        "in_progress": count(orders.c.status.in_(["Confirmed", "Assigned", "In Progress", "On Hold"])),
        "completed": count(orders.c.status.in_(["Completed", "Ready / Dispatched"])),
        "delayed": count(orders.c.requested_date < today, orders.c.status.not_in(NOT_DELAYABLE)),
        "due_today": count(orders.c.requested_date == today, orders.c.status.not_in(NOT_DELAYABLE)),
        "by_status": by_status,
        "by_department": by_department,
        "per_day": per_day,
        "shop_orders_today": count(orders.c.created_at >= start_of_day, orders.c.extraction_method == "shop"),
        "low_stock_count": len(low_stock),
        "low_stock": low_stock[:8],
        # Money still to collect on live and finished orders (cancelled orders are excluded).
        "unpaid_orders": count(orders.c.payment_status != "Paid", orders.c.amount_due.is_not(None),
                               orders.c.status != "Cancelled"),
        "amount_outstanding": float(db.scalar(
            select(func.coalesce(func.sum(orders.c.amount_due - orders.c.amount_paid), 0)).select_from(orders)
            .where(orders.c.amount_due.is_not(None), orders.c.status != "Cancelled")) or 0),
        "amount_not_set": count(orders.c.amount_due.is_(None), orders.c.status.not_in(["New", "Needs Review", "Cancelled"])),
        "failed_messages": db.scalar(select(func.count()).select_from(Message)
                                     .where(Message.processing_state == "failed")) if user.role in OFFICE else 0,
    }


@router.get("/activity")
def activity(limit: int = 30, user: User = Depends(require_roles(*MANAGERS, "operator")),
             db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 200))).all()
    order_ids = {r.entity_id for r in rows if r.entity_type == "order" and r.entity_id}
    numbers = dict(db.execute(select(Order.id, Order.order_number).where(Order.id.in_(order_ids))).all()) if order_ids else {}
    product_ids = {r.entity_id for r in rows if r.entity_type == "product" and r.entity_id}
    codes = dict(db.execute(select(Product.id, Product.product_code).where(Product.id.in_(product_ids))).all()) if product_ids else {}
    return [{
        "id": r.id, "timestamp": r.timestamp, "user": r.user.display_name if r.user else "System",
        "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id, "details": r.details,
        "entity_label": numbers.get(r.entity_id) if r.entity_type == "order"
        else codes.get(r.entity_id) if r.entity_type == "product" else None,
    } for r in rows]
