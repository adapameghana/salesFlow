from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Department, User
from ..schemas import DepartmentIn, DepartmentOut
from ..security import MANAGERS, get_current_user, require_roles
from ..services.audit import audit

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Department).order_by(Department.department_name)).all()


@router.post("", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, user: User = Depends(require_roles(*MANAGERS)),
                      db: Session = Depends(get_db)):
    dept = Department(**body.model_dump())
    db.add(dept)
    db.flush()
    audit(db, user, "department_created", "department", dept.id, dept.department_name)
    db.commit()
    return dept


@router.put("/{dept_id}", response_model=DepartmentOut)
def update_department(dept_id: int, body: DepartmentIn, user: User = Depends(require_roles(*MANAGERS)),
                      db: Session = Depends(get_db)):
    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(404, "Department not found")
    for key, value in body.model_dump().items():
        setattr(dept, key, value)
    audit(db, user, "department_updated", "department", dept.id, dept.department_name)
    db.commit()
    return dept


@router.get("/{dept_id}/users")
def department_users(dept_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.department_id == dept_id, User.active.is_(True))
                       .order_by(User.display_name)).all()
    return [{"id": u.id, "display_name": u.display_name} for u in users]
