from sqlalchemy.orm import Session

from ..models import AuditLog, User


def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id: int | None, details: str = "") -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or None,
    ))
