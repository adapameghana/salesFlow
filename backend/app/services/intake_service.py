"""Turns an incoming message (simulator, import or a future WhatsApp connector) into an order draft."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Branch, Message, Product, User
from .ai_parser import parse_with_ai
from .audit import audit
from .message_parser import BranchRef, ParsedOrder, ProductRef, parse_message
from .order_service import create_order_from_parsed

DUPLICATE_WINDOW = timedelta(minutes=30)


def load_reference_data(db: Session) -> tuple[list[ProductRef], list[BranchRef]]:
    products = db.scalars(select(Product).where(Product.active.is_(True))).all()
    branches = db.scalars(select(Branch).where(Branch.active.is_(True))).all()
    return (
        [ProductRef(p.id, p.product_code, p.product_name, p.unit, p.alias_list) for p in products],
        [BranchRef(b.id, b.branch_name, b.address) for b in branches],
    )


def extract(db: Session, text: str, received: datetime, sender_name: str | None,
            sender_reference: str | None, use_ai: bool) -> ParsedOrder:
    catalogue, branches = load_reference_data(db)
    local_received = received.astimezone(get_settings().business_tz)
    if use_ai and get_settings().ai_enabled:
        return parse_with_ai(text, local_received, catalogue, branches, sender_name, sender_reference)
    return parse_message(text, local_received, catalogue, branches, sender_name, sender_reference)


def find_duplicate(db: Session, source: str, external_id: str | None, sender: str | None, text: str) -> Message | None:
    if external_id:
        existing = db.scalar(select(Message).where(
            Message.source == source, Message.external_message_id == external_id))
        if existing:
            return existing
    if sender:
        since = datetime.now(timezone.utc) - DUPLICATE_WINDOW
        return db.scalar(select(Message).where(
            Message.sender_reference == sender,
            Message.message_text == text,
            Message.received_at >= since,
            Message.linked_order_id.is_not(None),
        ).order_by(Message.id.desc()))
    return None


def import_message(db: Session, payload, user: User | None) -> dict:
    text = payload.message_text.strip()
    duplicate = find_duplicate(db, payload.source, payload.external_message_id, payload.sender_reference, text)
    if duplicate is not None:
        same_id = payload.external_message_id and duplicate.external_message_id == payload.external_message_id
        if not same_id:
            # Same text resent by the same sender: keep the copy for traceability, but no new order.
            db.add(Message(
                source=payload.source, external_message_id=payload.external_message_id,
                sender_reference=payload.sender_reference, sender_name=payload.sender_name,
                message_text=text, processing_state="duplicate", linked_order_id=duplicate.linked_order_id,
                error_text=f"Same text as message #{duplicate.id} received within {DUPLICATE_WINDOW.seconds // 60} minutes",
            ))
        audit(db, user, "duplicate_message", "message", duplicate.id,
              "Same message ID received again" if same_id else "Repeated text from same sender")
        db.commit()
        return {"duplicate": True, "message": duplicate, "order": duplicate.linked_order,
                "detail": "Duplicate message ignored - no new order was created."}

    message = Message(
        source=payload.source, external_message_id=payload.external_message_id,
        sender_reference=payload.sender_reference, sender_name=payload.sender_name,
        message_text=text, received_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.flush()
    try:
        parsed = extract(db, text, message.received_at, payload.sender_name, payload.sender_reference, payload.use_ai)
        order = create_order_from_parsed(db, parsed, user, f"Created from {payload.source} message #{message.id}")
        message.linked_order_id = order.id
        message.processing_state = "needs_review" if parsed.flags else "parsed"
        audit(db, user, "message_imported", "message", message.id, f"Linked to {order.order_number}")
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = Message(
            source=payload.source, external_message_id=payload.external_message_id,
            sender_reference=payload.sender_reference, sender_name=payload.sender_name,
            message_text=text, processing_state="failed", error_text=str(exc)[:500],
        )
        db.add(failed)
        db.commit()
        return {"duplicate": False, "message": failed, "order": None,
                "detail": "Message stored but processing failed. It can be retried from the inbox."}
    db.refresh(message)
    return {"duplicate": False, "message": message, "order": message.linked_order,
            "detail": "Order draft created." if not order.review_flags else "Order draft created - needs review."}


def retry_message(db: Session, message: Message, user: User | None, use_ai: bool) -> Message:
    parsed = extract(db, message.message_text, message.received_at, message.sender_name,
                     message.sender_reference, use_ai)
    order = create_order_from_parsed(db, parsed, user, f"Created on retry of message #{message.id}")
    message.linked_order_id = order.id
    message.processing_state = "needs_review" if parsed.flags else "parsed"
    message.error_text = None
    audit(db, user, "message_retried", "message", message.id, f"Linked to {order.order_number}")
    db.commit()
    return message
