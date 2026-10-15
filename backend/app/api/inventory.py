"""Stock levels, stock received, adjustments and the movement history of each product."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, StockMovement, User
from ..schemas import StockAdjust, StockReceive
from ..security import get_current_user
from ..services import stock_service as stock
from ..services.audit import audit

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def row(product: Product, user: User) -> dict:
    return {
        "id": product.id,
        "product_code": product.product_code,
        "product_name": product.product_name,
        "unit": product.unit,
        "department_id": product.department_id,
        "department_name": product.department.department_name if product.department else None,
        "active": product.active,
        "on_hand": float(product.stock_on_hand or 0),
        "reserved": float(product.stock_reserved or 0),
        "available": float(product.available),
        "reorder_level": float(product.reorder_level or 0),
        "level": stock.stock_level(product),
        "can_manage": stock.can_manage_stock(user, product),
    }


def visible_product(db: Session, product_id: int, user: User) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    if user.role == "department" and product.department_id != user.department_id:
        raise HTTPException(403, "This product belongs to another department")
    return product


def managed_product(db: Session, product_id: int, user: User) -> Product:
    product = visible_product(db, product_id, user)
    if not stock.can_manage_stock(user, product):
        raise HTTPException(403, "Only managers or the product's own department can change its stock")
    return product


@router.get("")
def list_stock(
    q: str | None = None,
    department_id: int | None = None,
    level: str | None = Query(None, pattern="^(ok|low|out)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Product).order_by(Product.product_name)
    if user.role == "department":
        query = query.where(Product.department_id == user.department_id)
    elif department_id:
        query = query.where(Product.department_id == department_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Product.product_name.ilike(like), Product.product_code.ilike(like)))
    rows = [row(p, user) for p in db.scalars(query).all()]
    if level:
        rows = [r for r in rows if r["level"] == level]
    return rows


@router.post("/{product_id}/receive")
def receive_stock(product_id: int, body: StockReceive, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    product = managed_product(db, product_id, user)
    stock.receive(db, product, body.quantity, user, body.reason)
    audit(db, user, "stock_received", "product", product.id,
          f"+{stock.fmt(body.quantity)} {product.unit}" + (f" ({body.reason.strip()})" if (body.reason or "").strip() else ""))
    db.commit()
    db.refresh(product)
    return row(product, user)


@router.post("/{product_id}/adjust")
def adjust_stock(product_id: int, body: StockAdjust, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    product = managed_product(db, product_id, user)
    stock.adjust(db, product, body.delta, user, body.reason)
    sign = "+" if body.delta > 0 else ""
    audit(db, user, "stock_adjusted", "product", product.id,
          f"{sign}{stock.fmt(body.delta)} {product.unit} ({body.reason.strip()})")
    db.commit()
    db.refresh(product)
    return row(product, user)


@router.get("/{product_id}/movements")
def movements(product_id: int, limit: int = Query(50, ge=1, le=500),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    visible_product(db, product_id, user)
    rows = db.scalars(select(StockMovement).where(StockMovement.product_id == product_id)
                      .order_by(StockMovement.id.desc()).limit(limit)).all()
    return [{
        "id": m.id, "type": m.movement_type, "quantity": float(m.quantity),
        "on_hand_after": float(m.on_hand_after), "reserved_after": float(m.reserved_after),
        "order_id": m.order_id, "order_number": m.order.order_number if m.order else None,
        "user": m.user.display_name if m.user else "System",
        "reason": m.reason, "created_at": m.created_at,
    } for m in rows]
