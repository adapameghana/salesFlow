"""AI voice-call payment reminders: call log, follow-ups, manual/test calls and the voice agent's callbacks."""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Order, PaymentReminderCall, User
from ..schemas import ReminderHandledIn, ReminderResultIn, ReminderSettingsIn
from ..security import MANAGERS, OFFICE, require_roles
from ..services import order_service as svc
from ..services import reminder_service as rem
from ..services.payment_service import balance
from ..services.scheduler import run_locked_cycle

router = APIRouter(prefix="/api", tags=["reminders"])


def today() -> date:
    return get_settings().business_now().date()


def get_call_or_404(db: Session, call_id: int) -> PaymentReminderCall:
    call = db.get(PaymentReminderCall, call_id)
    if call is None:
        raise HTTPException(404, "Reminder call not found")
    return call


# ---------------------------------------------------------------- staff views

@router.get("/reminders")
def list_calls(
    status: list[str] | None = Query(None),
    intent: list[str] | None = Query(None),
    needs_followup: bool | None = None,
    order_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user: User = Depends(require_roles(*OFFICE)),
    db: Session = Depends(get_db),
):
    query = select(PaymentReminderCall)
    if status:
        query = query.where(PaymentReminderCall.status.in_(status))
    if intent:
        query = query.where(PaymentReminderCall.intent.in_(intent))
    if needs_followup is not None:
        query = query.where(PaymentReminderCall.needs_followup.is_(needs_followup))
    if order_id:
        query = query.where(PaymentReminderCall.order_id == order_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(PaymentReminderCall.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [rem.call_summary(c) for c in rows]}


@router.get("/reminders/due")
def due_today(user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    s = get_settings()
    now = s.business_now()
    orders = rem.due_orders(db, now)
    return {
        "enabled": s.reminders_enabled, "in_window": rem.in_window(now), "window": rem.window_label(),
        "max_attempts": s.reminder_max_attempts,
        "items": [{
            "order_id": o.id, "order_number": o.order_number, "customer_name": o.customer_name,
            "phone": rem.mobile_number(o.contact_reference), "language": o.preferred_language,
            "balance": float(balance(o)), "attempts": rem.attempts(o), "last_call_at": rem.last_call_at(o),
            "payment_promised_date": o.payment_promised_date,
        } for o in orders],
    }


@router.get("/reminders/promised")
def promised(user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    orders = db.scalars(select(Order).where(
        Order.payment_promised_date.is_not(None), Order.payment_promised_date >= today(),
        Order.payment_status != "Paid", Order.status != "Cancelled",
    ).order_by(Order.payment_promised_date)).all()
    return {"items": [{
        "order_id": o.id, "order_number": o.order_number, "customer_name": o.customer_name,
        "phone": rem.mobile_number(o.contact_reference),
        "balance": float(b) if (b := balance(o)) is not None else None,
        "payment_promised_date": o.payment_promised_date,
    } for o in orders]}


@router.get("/reminders/agent-status")
def agent_status(user: User = Depends(require_roles(*OFFICE))):
    return rem.agent_status()


@router.post("/reminders/run")
def run_now(user: User = Depends(require_roles(*MANAGERS))):
    result = run_locked_cycle(user_id=user.id)
    if result is None:
        raise HTTPException(409, "A reminder round is already running")
    return result


@router.get("/reminders/{call_id}")
def get_call(call_id: int, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    return rem.call_detail(get_call_or_404(db, call_id))


@router.get("/reminders/{call_id}/recording")
def get_recording(call_id: int, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    call = get_call_or_404(db, call_id)
    path = Path(call.recording_path) if call.recording_path else None
    if path is None or not path.is_file():
        raise HTTPException(404, "No recording for this call")
    return FileResponse(path, media_type="audio/wav", filename=f"reminder_call_{call.id}.wav")


@router.post("/reminders/{call_id}/handled")
def handled(call_id: int, body: ReminderHandledIn, user: User = Depends(require_roles(*OFFICE)),
            db: Session = Depends(get_db)):
    call = rem.mark_handled(db, get_call_or_404(db, call_id), user, body.note)
    return rem.call_summary(call)


# ---------------------------------------------------------------- per order

@router.post("/orders/{order_id}/reminders/call", status_code=201)
def call_now(order_id: int, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    call = rem.start_call(db, order, user, today())
    if call.status == "failed":
        raise HTTPException(503, call.error or "The call could not be started")
    return rem.call_summary(call)


@router.post("/orders/{order_id}/reminders/test", status_code=201)
def test_call(order_id: int, user: User = Depends(require_roles(*OFFICE)), db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    call, ws_url = rem.start_test_call(db, order, user, today())
    return {"call_id": call.id, "ws_url": ws_url}


@router.patch("/orders/{order_id}/reminder-settings")
def reminder_settings(order_id: int, body: ReminderSettingsIn, user: User = Depends(require_roles(*OFFICE)),
                      db: Session = Depends(get_db)):
    order = svc.get_order_or_404(db, order_id)
    rem.update_settings(db, order, body.model_dump(exclude_unset=True), user)
    db.refresh(order)
    return svc.order_detail(order, user, today())


# ---------------------------------------------------------------- voice agent callbacks (shared secret)

@router.get("/internal/reminders/{call_id}/context")
def agent_context(call_id: int, x_agent_secret: str | None = Header(None), db: Session = Depends(get_db)):
    rem.check_agent_secret(x_agent_secret)
    call = get_call_or_404(db, call_id)
    return {"call_id": call.id, "phone": call.phone, "context": rem.call_context(call.order, today())}


@router.get("/internal/reminder-context")
def order_context(order: str, x_agent_secret: str | None = Header(None), db: Session = Depends(get_db)):
    """Context for an order (by id or order number), used by the agent's prepare tool before a demo."""
    rem.check_agent_secret(x_agent_secret)
    found = db.scalar(select(Order).where(Order.order_number == order.strip()))
    if found is None and order.strip().isdigit():
        found = db.get(Order, int(order))
    if found is None:
        raise HTTPException(404, f"Order {order} not found")
    return {"order_id": found.id, "context": rem.call_context(found, today())}


@router.post("/internal/reminders/{call_id}/result")
def agent_result(call_id: int, body: ReminderResultIn, x_agent_secret: str | None = Header(None),
                 db: Session = Depends(get_db)):
    rem.check_agent_secret(x_agent_secret)
    call = get_call_or_404(db, call_id)
    call = rem.record_result(db, call, body.model_dump(), today())
    return {"ok": True, "status": call.status, "needs_followup": call.needs_followup}
