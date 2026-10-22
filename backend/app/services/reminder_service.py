"""AI voice-call payment reminders: who to call, starting calls, and saving what the customer said.

The calls themselves are made by the separate voice_agent service (Asterisk + open-source speech AI).
This module decides *which* orders are due, asks the agent to dial, and stores the result it reports.
See docs/PAYMENT_REMINDERS.md for the rules and the interface contract.
"""
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Order, PaymentReminderCall, User
from ..security import OFFICE
from .audit import audit
from .message_parser import PHONE_RE
from .payment_service import balance

log = logging.getLogger(__name__)

LANGUAGES = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil"}
INTENTS = ("paid_claimed", "will_pay", "ask_details", "callback", "dispute",
           "wrong_number", "not_interested", "no_response", "other")
RESULT_STATUSES = ("answered", "no_answer", "busy", "failed")
FOLLOWUP_INTENTS = {"paid_claimed", "callback", "dispute", "other"}  # staff must act
STOP_INTENTS = {"wrong_number", "not_interested"}  # never call this order again
IN_FLIGHT = ("queued", "dialing")
COUNTED = ("answered", "no_answer", "busy")  # failed calls (agent/line down) are not counted as attempts
STALE_AFTER = timedelta(minutes=60)  # an in-flight call with no result after this is marked failed
MAX_RECORDING_BYTES = 20 * 1024 * 1024


# ---------------------------------------------------------------- helpers

def mobile_number(contact_reference: str | None) -> str | None:
    """The 10-digit Indian mobile number in the contact reference, or None."""
    match = PHONE_RE.search(contact_reference or "")
    return re.sub(r"\D", "", match.group(1)) if match else None


def in_window(now: datetime) -> bool:
    s = get_settings()
    return s.reminder_window_start <= now.hour < s.reminder_window_end


def window_label() -> str:
    s = get_settings()
    return f"{s.reminder_window_start:02d}:00–{s.reminder_window_end:02d}:00"


def phone_calls(order: Order) -> list[PaymentReminderCall]:
    """Real phone calls for the order (browser test calls excluded)."""
    return [c for c in order.reminder_calls if c.provider != "browser"]


def attempts(order: Order) -> int:
    return sum(1 for c in phone_calls(order) if c.status in COUNTED)


def last_call_at(order: Order) -> datetime | None:
    calls = phone_calls(order)
    return max((c.created_at for c in calls if c.created_at), default=None)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_token(call_id: int) -> str:
    """Token that lets the browser open a test call on the voice agent (HMAC of the call id)."""
    secret = get_settings().voice_agent_secret.encode()
    return hmac.new(secret, str(call_id).encode(), hashlib.sha256).hexdigest()


def check_agent_secret(header_value: str | None) -> None:
    expected = get_settings().voice_agent_secret
    if not header_value or not hmac.compare_digest(header_value, expected):
        raise HTTPException(401, "Bad voice agent secret")


# ---------------------------------------------------------------- eligibility

def why_not_callable(order: Order, today: date | None = None) -> str | None:
    """Reason this order cannot get a reminder call right now (ignoring schedule rules), or None."""
    if order.status == "Cancelled":
        return "The order is cancelled"
    if order.payment_status == "Paid":
        return "The order is already paid"
    bal = balance(order)
    if bal is None or bal <= 0:
        return "The order has no balance due"
    if mobile_number(order.contact_reference) is None:
        return "The order has no valid mobile number"
    if any(c.status in IN_FLIGHT for c in phone_calls(order)):
        return "A reminder call is already in progress"
    return None


def is_due(order: Order, now: datetime) -> bool:
    """Scheduler rules on top of why_not_callable."""
    s = get_settings()
    if not order.reminders_enabled or why_not_callable(order) is not None:
        return False
    if order.payment_promised_date and now.date() < order.payment_promised_date:
        return False
    if order.created_at and _aware(order.created_at) > now - timedelta(hours=s.reminder_first_after_hours):
        return False
    if attempts(order) >= s.reminder_max_attempts:
        return False
    last = last_call_at(order)
    return last is None or _aware(last) <= now - timedelta(hours=s.reminder_gap_hours)


def candidate_query():
    """Cheap SQL pre-filter; is_due() makes the final decision."""
    return (select(Order)
            .where(Order.payment_status != "Paid", Order.amount_due.is_not(None), Order.amount_due > 0,
                   Order.status != "Cancelled", Order.reminders_enabled.is_(True))
            .options(selectinload(Order.reminder_calls)))


def due_orders(db: Session, now: datetime) -> list[Order]:
    orders = db.scalars(candidate_query().order_by(Order.created_at)).all()
    return [o for o in orders if is_due(o, now)]


# ---------------------------------------------------------------- calls

def call_context(order: Order, today: date) -> dict:
    """Everything the agent may say. It must never state facts that are not in here."""
    bal = balance(order)
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "language": order.preferred_language or "en",
        "balance": float(bal) if bal is not None else None,
        "amount_due": float(order.amount_due) if order.amount_due is not None else None,
        "amount_paid": float(order.amount_paid or 0),
        "business_name": get_settings().business_name,
        "attempt_no": attempts(order) + 1,
        "items": [{"name": i.product_name, "quantity": float(i.quantity) if i.quantity is not None else None,
                   "unit": i.unit} for i in order.items],
        "today": today.isoformat(),
    }


def _post_agent(path: str, payload: dict, timeout: int = 10) -> None:
    s = get_settings()
    req = urllib.request.Request(
        f"{s.voice_agent_url.rstrip('/')}{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Agent-Secret": s.voice_agent_secret})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status not in (200, 201, 202):
            raise RuntimeError(f"voice agent answered HTTP {resp.status}")


def agent_status() -> dict:
    url = f"{get_settings().voice_agent_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return {"reachable": True, "detail": json.load(resp)}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"reachable": False, "detail": str(exc)}


def start_call(db: Session, order: Order, user: User | None, today: date) -> PaymentReminderCall:
    """Create the call row and ask the voice agent to dial. Commits."""
    reason = why_not_callable(order)
    if reason:
        raise HTTPException(422, reason)
    context = call_context(order, today)
    call = PaymentReminderCall(
        order_id=order.id, attempt_no=context["attempt_no"], phone=mobile_number(order.contact_reference),
        language=context["language"], amount_due_at_call=balance(order), provider="asterisk",
        status="queued", started_by=user.id if user else None,
    )
    order.reminder_calls.append(call)
    db.flush()
    audit(db, user, "reminder_call_started", "order", order.id,
          f"attempt {call.attempt_no} to {call.phone} in {LANGUAGES.get(call.language, call.language)}")
    db.commit()
    try:
        _post_agent("/calls", {"call_id": call.id, "phone": call.phone, "context": context})
        call.status = "dialing"
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        log.warning("Voice agent could not start call %s: %s", call.id, exc)
        call.status = "failed"
        call.error = f"Voice agent unavailable: {exc}"
        call.completed_at = datetime.now(timezone.utc)
    db.commit()
    return call


def start_test_call(db: Session, order: Order, user: User, today: date) -> tuple[PaymentReminderCall, str]:
    """A browser test call: staff talk to the agent with their microphone. Does not change the order."""
    if order.amount_due is None:
        raise HTTPException(422, "Set the order amount first")
    call = PaymentReminderCall(
        order_id=order.id, attempt_no=0, phone=mobile_number(order.contact_reference),
        language=order.preferred_language or "en", amount_due_at_call=balance(order),
        provider="browser", status="test", started_by=user.id,
    )
    order.reminder_calls.append(call)
    db.flush()
    audit(db, user, "reminder_test_call", "order", order.id, "")
    db.commit()
    ws = get_settings().voice_agent_ws_url.rstrip("/")
    return call, f"{ws}/test?call_id={call.id}&token={test_token(call.id)}"


def expire_stale_calls(db: Session, now: datetime) -> int:
    """Calls the agent never reported back on (agent crashed or restarted)."""
    cutoff = now - STALE_AFTER
    stale = db.scalars(select(PaymentReminderCall).where(
        PaymentReminderCall.status.in_(IN_FLIGHT), PaymentReminderCall.created_at < cutoff)).all()
    for call in stale:
        call.status = "failed"
        call.error = "No result from the voice agent"
        call.completed_at = now
    if stale:
        db.commit()
    return len(stale)


def run_reminder_cycle(db: Session, now: datetime | None = None, user: User | None = None) -> dict:
    """One scheduler pass: call every order that is due (up to reminder_calls_per_cycle)."""
    s = get_settings()
    now = now or s.business_now()
    expire_stale_calls(db, now)
    if not in_window(now):
        return {"started": 0, "message": f"Outside calling hours ({window_label()}); no calls made"}
    due = due_orders(db, now)
    started = 0
    for order in due[: s.reminder_calls_per_cycle]:
        try:
            call = start_call(db, order, user, now.date())
        except HTTPException:
            db.rollback()
            continue
        if call.status == "failed":
            # The agent is down: stop here instead of creating a failed row for every order.
            return {"started": started, "message": f"Voice agent unavailable: {call.error}"}
        started += 1
    left = max(0, len(due) - started)
    msg = f"Started {started} call(s)" + (f"; {left} more next round" if left else "")
    return {"started": started, "message": msg}


# ---------------------------------------------------------------- results

def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _save_recording(call_id: int, b64: str | None) -> str | None:
    if not b64:
        return None
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        log.warning("Bad recording for call %s", call_id)
        return None
    if len(data) > MAX_RECORDING_BYTES or not data.startswith(b"RIFF"):
        log.warning("Recording for call %s rejected (size/format)", call_id)
        return None
    folder = Path(get_settings().reminder_recordings_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"call_{call_id}.wav"
    path.write_bytes(data)
    return str(path)


def record_result(db: Session, call: PaymentReminderCall, data: dict, today: date) -> PaymentReminderCall:
    """Store what the voice agent reports and apply its effect on the order."""
    status = data.get("status")
    if status not in RESULT_STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(RESULT_STATUSES)}")
    intent = data.get("intent")
    if intent is not None and intent not in INTENTS:
        intent = "other"
    test = call.provider == "browser"
    # Demo mode: let browser test calls update the order the way a real call would.
    applies = not test or get_settings().reminder_test_calls_apply

    call.status = "test" if test else status
    call.intent = intent
    call.promised_date = _parse_date(data.get("promised_date"))
    transcript = data.get("transcript")
    call.transcript = [
        {"speaker": "agent" if t.get("speaker") == "agent" else "customer",
         "text": str(t.get("text", ""))[:2000], "ts": t.get("ts")}
        for t in transcript if isinstance(t, dict)
    ][:200] if isinstance(transcript, list) else None
    call.summary = (data.get("summary") or None) and str(data["summary"])[:2000]
    call.duration_seconds = int(data["duration_seconds"]) if data.get("duration_seconds") is not None else None
    call.error = (data.get("error") or None) and str(data["error"])[:2000]
    call.completed_at = datetime.now(timezone.utc)
    call.recording_path = _save_recording(call.id, data.get("recording_wav_base64")) or call.recording_path

    order = call.order
    effect = ""
    if applies and status == "answered":
        call.needs_followup = intent in FOLLOWUP_INTENTS
        if intent == "will_pay" and call.promised_date and call.promised_date >= today:
            order.payment_promised_date = call.promised_date
            effect = f"; promised to pay on {call.promised_date.isoformat()}"
        elif intent in STOP_INTENTS:
            order.reminders_enabled = False
            effect = "; reminders turned off"
    audit(db, None, "reminder_call_result", "order", order.id,
          f"{'test ' if test else ''}call {call.id}: {call.status}, {intent or 'no intent'}{effect}")
    db.commit()
    return call


def mark_handled(db: Session, call: PaymentReminderCall, user: User, note: str | None) -> PaymentReminderCall:
    if not call.needs_followup:
        raise HTTPException(400, "This call does not need follow-up")
    call.needs_followup = False
    call.handled_by = user.id
    call.handled_at = datetime.now(timezone.utc)
    call.handled_note = (note or "").strip() or None
    audit(db, user, "reminder_followup_handled", "order", call.order_id,
          f"call {call.id}" + (f": {call.handled_note}" if call.handled_note else ""))
    db.commit()
    return call


def update_settings(db: Session, order: Order, changes: dict, user: User) -> None:
    # None means "clear" only for the promised date; the other two are required columns.
    changes = {k: v for k, v in changes.items()
               if k == "payment_promised_date" or (k in ("preferred_language", "reminders_enabled") and v is not None)}
    if "preferred_language" in changes and changes["preferred_language"] not in LANGUAGES:
        raise HTTPException(422, "Language must be one of en, hi, te, ta")
    for key, value in changes.items():
        setattr(order, key, value)
    audit(db, user, "reminder_settings_updated", "order", order.id,
          ", ".join(f"{k}={v}" for k, v in changes.items()))
    db.commit()


# ---------------------------------------------------------------- serialization

def _num(value: Decimal | None):
    return None if value is None else float(value)


def call_summary(call: PaymentReminderCall) -> dict:
    order = call.order
    return {
        "id": call.id, "order_id": call.order_id,
        "order_number": order.order_number if order else None,
        "customer_name": order.customer_name if order else None,
        "attempt_no": call.attempt_no, "phone": call.phone, "language": call.language,
        "amount_due_at_call": _num(call.amount_due_at_call), "provider": call.provider,
        "status": call.status, "intent": call.intent, "promised_date": call.promised_date,
        "summary": call.summary, "duration_seconds": call.duration_seconds,
        "has_recording": bool(call.recording_path and Path(call.recording_path).is_file()),
        "needs_followup": call.needs_followup,
        "handled_by_name": call.handler.display_name if call.handler else None,
        "handled_at": call.handled_at, "handled_note": call.handled_note,
        "created_at": call.created_at, "completed_at": call.completed_at, "error": call.error,
    }


def call_detail(call: PaymentReminderCall) -> dict:
    return {**call_summary(call), "transcript": call.transcript or []}


def order_reminder_info(order: Order, user: User) -> dict:
    """Extra fields for the order detail page."""
    return {
        "preferred_language": order.preferred_language or "en",
        "reminders_enabled": order.reminders_enabled,
        "payment_promised_date": order.payment_promised_date,
        "reminder_attempts": attempts(order),
        "reminder_calls": [call_summary(c) for c in sorted(order.reminder_calls, key=lambda c: c.id, reverse=True)],
        "can_call_reminder": user.role in OFFICE and why_not_callable(order) is None,
    }
