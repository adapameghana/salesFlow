"""Master data maintenance: users, products, branches and routing rules."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Branch, Product, RoutingRule, User
from ..schemas import (
    BranchIn, BranchOut, ProductIn, ProductOut, RoutingRuleIn, RoutingRuleOut, UserCreate, UserOut, UserUpdate,
)
from ..security import MANAGERS, ROLES, get_current_user, hash_password, require_roles
from ..services.audit import audit
from .auth import user_out

router = APIRouter(prefix="/api", tags=["admin"])
managers = require_roles(*MANAGERS)


def commit_or_409(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"{what} already exists")


# ------------------------------------------------------------------ users

@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(managers), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, user: User = Depends(managers), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, f"Role must be one of {', '.join(ROLES)}")
    if body.role == "department" and not body.department_id:
        raise HTTPException(422, "Department users need a department")
    new = User(display_name=body.display_name, username=body.username.strip().lower(),
               password_hash=hash_password(body.password), role=body.role,
               department_id=body.department_id if body.role == "department" else None)
    db.add(new)
    commit_or_409(db, "Username")
    audit(db, user, "user_created", "user", new.id, f"{new.username} ({new.role})")
    db.commit()
    db.refresh(new)
    return user_out(new)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, user: User = Depends(managers), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in ROLES:
        raise HTTPException(422, "Invalid role")
    if target.id == user.id and data.get("active") is False:
        raise HTTPException(400, "You cannot disable your own account")
    if data.get("password"):
        target.password_hash = hash_password(data.pop("password"))
    data.pop("password", None)
    for key, value in data.items():
        setattr(target, key, value)
    audit(db, user, "user_updated", "user", target.id, ", ".join(sorted(body.model_fields_set - {"password"})))
    db.commit()
    db.refresh(target)
    return user_out(target)


# ------------------------------------------------------------------ products

@router.get("/products", response_model=list[ProductOut])
def list_products(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.product_name)).all()


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    product = Product(**body.model_dump())
    db.add(product)
    commit_or_409(db, "Product code")
    audit(db, user, "product_created", "product", product.id, product.product_code)
    db.commit()
    return product


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    for key, value in body.model_dump().items():
        setattr(product, key, value)
    audit(db, user, "product_updated", "product", product.id, product.product_code)
    commit_or_409(db, "Product code")
    return product


# ------------------------------------------------------------------ branches

@router.get("/branches", response_model=list[BranchOut])
def list_branches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Branch).order_by(Branch.branch_name)).all()


@router.post("/branches", response_model=BranchOut, status_code=201)
def create_branch(body: BranchIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    branch = Branch(**body.model_dump())
    db.add(branch)
    commit_or_409(db, "Branch")
    audit(db, user, "branch_created", "branch", branch.id, branch.branch_name)
    db.commit()
    return branch


@router.put("/branches/{branch_id}", response_model=BranchOut)
def update_branch(branch_id: int, body: BranchIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(404, "Branch not found")
    for key, value in body.model_dump().items():
        setattr(branch, key, value)
    audit(db, user, "branch_updated", "branch", branch.id, branch.branch_name)
    commit_or_409(db, "Branch")
    return branch


# ------------------------------------------------------------------ routing rules

@router.get("/routing-rules", response_model=list[RoutingRuleOut])
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(RoutingRule).order_by(RoutingRule.priority, RoutingRule.id)).all()


@router.post("/routing-rules", response_model=RoutingRuleOut, status_code=201)
def create_rule(body: RoutingRuleIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    rule = RoutingRule(**body.model_dump())
    db.add(rule)
    db.flush()
    audit(db, user, "rule_created", "routing_rule", rule.id, rule.rule_name)
    db.commit()
    return rule


@router.put("/routing-rules/{rule_id}", response_model=RoutingRuleOut)
def update_rule(rule_id: int, body: RoutingRuleIn, user: User = Depends(managers), db: Session = Depends(get_db)):
    rule = db.get(RoutingRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    audit(db, user, "rule_updated", "routing_rule", rule.id, rule.rule_name)
    db.commit()
    return rule


@router.delete("/routing-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: User = Depends(managers), db: Session = Depends(get_db)):
    rule = db.get(RoutingRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    audit(db, user, "rule_deleted", "routing_rule", rule.id, rule.rule_name)
    db.delete(rule)
    db.commit()
