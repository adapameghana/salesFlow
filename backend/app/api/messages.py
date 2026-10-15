from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Message, User
from ..schemas import MessageImport, MessageOut, MessagePreview, RetryRequest
from ..security import OFFICE, require_roles
from ..services import intake_service
from ..services.order_service import order_detail

router = APIRouter(prefix="/api/messages", tags=["messages"])


def message_out(m: Message) -> MessageOut:
    out = MessageOut.model_validate(m)
    if m.linked_order:
        out.linked_order_number = m.linked_order.order_number
        out.linked_order_status = m.linked_order.status
    return out


@router.get("", response_model=list[MessageOut])
def list_messages(state: str | None = None, limit: int = 100,
                  user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    query = select(Message).order_by(Message.received_at.desc(), Message.id.desc()).limit(min(limit, 500))
    if state:
        query = query.where(Message.processing_state == state)
    return [message_out(m) for m in db.scalars(query).all()]


@router.post("/import")
def import_message(body: MessageImport, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    result = intake_service.import_message(db, body, user)
    order = result["order"]
    today = get_settings().business_now().date()
    return {
        "duplicate": result["duplicate"],
        "detail": result["detail"],
        "message": message_out(result["message"]),
        "order": order_detail(order, user, today) if order else None,
    }


@router.post("/preview")
def preview(body: MessagePreview, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    """Parse a message without saving anything - useful to compare rules vs AI extraction."""
    parsed = intake_service.extract(db, body.message_text, datetime.now(timezone.utc),
                                    body.sender_name, body.sender_reference, body.use_ai)
    return {
        "method": parsed.method,
        "customer_name": parsed.customer_name,
        "contact_reference": parsed.contact_reference,
        "delivery_address": parsed.delivery_address,
        "requested_date": parsed.requested_date,
        "items": [vars(i) for i in parsed.items],
        "notes": parsed.notes,
        "flags": parsed.flags,
    }


@router.post("/{message_id}/retry")
def retry(message_id: int, body: RetryRequest, user: User = Depends(require_roles(*OFFICE)),
          db: Session = Depends(get_db)):
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    if message.processing_state != "failed":
        raise HTTPException(400, "Only failed messages can be retried")
    return message_out(intake_service.retry_message(db, message, user, body.use_ai))
