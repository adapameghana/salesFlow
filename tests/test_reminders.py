"""Unit tests for AI payment-reminder calls (no database, no voice agent). Run:  python -m pytest tests"""
import base64
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import get_settings  # noqa: E402
from app.models import Order, OrderItem, PaymentReminderCall, User  # noqa: E402
from app.services import reminder_service as rem  # noqa: E402

IST = timezone(timedelta(minutes=330))
NOW = datetime(2026, 10, 22, 11, 0, tzinfo=IST)
TODAY = NOW.date()


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass


def order(**kw):
    defaults = dict(id=1, order_number="ORD-1", customer_name="Sri Sai Clinic", contact_reference="+91 98765 43210",
                    status="Assigned", amount_due=Decimal("5000"), amount_paid=Decimal("750"),
                    payment_status="Partially Paid", preferred_language="te", reminders_enabled=True,
                    created_at=NOW - timedelta(days=2))
    defaults.update(kw)
    o = Order(**defaults)
    o.items.append(OrderItem(product_name="Nitrile gloves M", quantity=Decimal(5), unit="box"))
    return o


def call(o, status="answered", hours_ago=30, provider="asterisk", **kw):
    c = PaymentReminderCall(order_id=o.id, provider=provider, status=status, language="te",
                            created_at=NOW - timedelta(hours=hours_ago), **kw)
    o.reminder_calls.append(c)
    return c


# ---------------------------------------------------------------- phone numbers and window

@pytest.mark.parametrize("ref,expected", [
    ("+91 98765 43210", "9876543210"), ("9876543210", "9876543210"), ("Call 98765-43210 Ravi", "9876543210"),
    ("040 2345678", None), ("", None), (None, None),
])
def test_mobile_number(ref, expected):
    assert rem.mobile_number(ref) == expected


def test_calling_window():
    assert rem.in_window(NOW.replace(hour=10)) and rem.in_window(NOW.replace(hour=18, minute=59))
    assert not rem.in_window(NOW.replace(hour=9, minute=59)) and not rem.in_window(NOW.replace(hour=19))


# ---------------------------------------------------------------- who is due

def test_unpaid_order_is_due():
    assert rem.is_due(order(), NOW)


@pytest.mark.parametrize("change", [
    dict(payment_status="Paid", amount_paid=Decimal("5000")),
    dict(status="Cancelled"),
    dict(amount_due=None),
    dict(contact_reference="no phone"),
    dict(reminders_enabled=False),
    dict(created_at=NOW - timedelta(hours=5)),             # too new
    dict(payment_promised_date=TODAY + timedelta(days=2)),  # promised to pay later
])
def test_not_due(change):
    assert not rem.is_due(order(**change), NOW)


def test_promised_date_reached_is_due_again():
    assert rem.is_due(order(payment_promised_date=TODAY), NOW)


def test_gap_and_max_attempts():
    o = order()
    call(o, hours_ago=5)
    assert not rem.is_due(o, NOW)  # called 5h ago

    o = order()
    for h in (100, 70, 40):
        call(o, status="no_answer", hours_ago=h)
    assert rem.attempts(o) == 3 and not rem.is_due(o, NOW)


def test_failed_and_test_calls_do_not_count_as_attempts():
    o = order()
    call(o, status="failed", hours_ago=100)
    call(o, status="test", provider="browser", hours_ago=1)
    assert rem.attempts(o) == 0 and rem.is_due(o, NOW)


def test_call_in_progress_blocks_new_call():
    o = order()
    call(o, status="dialing", hours_ago=30)
    assert rem.why_not_callable(o) == "A reminder call is already in progress"


# ---------------------------------------------------------------- context sent to the agent

def test_call_context_only_has_order_facts():
    ctx = rem.call_context(order(), TODAY)
    assert ctx["balance"] == 4250.0 and ctx["language"] == "te" and ctx["attempt_no"] == 1
    assert ctx["items"] == [{"name": "Nitrile gloves M", "quantity": 5.0, "unit": "box"}]
    assert ctx["today"] == "2026-10-22"


def test_start_call_refuses_paid_order():
    with pytest.raises(HTTPException) as err:
        rem.start_call(FakeDB(), order(payment_status="Paid"), None, TODAY)
    assert err.value.status_code == 422


def test_start_call_marks_failed_when_agent_down(monkeypatch):
    def down(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(rem, "_post_agent", down)
    o = order()
    c = rem.start_call(FakeDB(), o, None, TODAY)
    assert c.status == "failed" and "unavailable" in c.error and c.phone == "9876543210"


def test_start_call_dialing(monkeypatch):
    sent = {}
    monkeypatch.setattr(rem, "_post_agent", lambda path, payload: sent.update(path=path, payload=payload))
    c = rem.start_call(FakeDB(), order(), None, TODAY)
    assert c.status == "dialing" and sent["path"] == "/calls" and sent["payload"]["phone"] == "9876543210"


def test_test_token_is_stable_and_secret_checked():
    assert rem.test_token(42) == rem.test_token(42) != rem.test_token(43)
    with pytest.raises(HTTPException):
        rem.check_agent_secret("wrong")
    rem.check_agent_secret(get_settings().voice_agent_secret)


# ---------------------------------------------------------------- results

def result(**kw):
    data = dict(status="answered", intent=None, promised_date=None, summary="s",
                transcript=[{"speaker": "agent", "text": "hello", "ts": 0}], duration_seconds=30,
                recording_wav_base64=None, error=None)
    data.update(kw)
    return data


def test_paid_claim_needs_followup_but_order_not_marked_paid():
    o = order()
    c = call(o, status="dialing")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="paid_claimed"), TODAY)
    assert c.needs_followup and c.status == "answered" and o.payment_status == "Partially Paid"


def test_will_pay_sets_promised_date_and_pauses_calls():
    o = order()
    c = call(o, status="dialing")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="will_pay", promised_date="2026-10-24"), TODAY)
    assert o.payment_promised_date == date(2026, 10, 24) and not c.needs_followup
    assert not rem.is_due(o, NOW + timedelta(days=1))


def test_past_promised_date_is_ignored():
    o = order()
    c = call(o, status="dialing")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="will_pay", promised_date="2026-10-01"), TODAY)
    assert o.payment_promised_date is None


@pytest.mark.parametrize("intent", ["wrong_number", "not_interested"])
def test_stop_intents_turn_reminders_off(intent):
    o = order()
    c = call(o, status="dialing")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent=intent), TODAY)
    assert o.reminders_enabled is False


def test_test_call_result_does_not_change_order(monkeypatch):
    monkeypatch.setattr(get_settings(), "reminder_test_calls_apply", False)
    o = order()
    c = call(o, status="test", provider="browser")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="not_interested"), TODAY)
    assert c.status == "test" and o.reminders_enabled is True and not c.needs_followup


def test_unknown_intent_becomes_other_and_bad_status_rejected():
    o = order()
    c = call(o, status="dialing")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="banana"), TODAY)
    assert c.intent == "other" and c.needs_followup
    with pytest.raises(HTTPException):
        rem.record_result(FakeDB(), c, result(status="exploded"), TODAY)


def test_recording_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "reminder_recordings_dir", str(tmp_path))
    o = order()
    c = call(o, status="dialing", id=7)
    c.order = o
    wav = base64.b64encode(b"RIFF" + b"\0" * 40).decode()
    rem.record_result(FakeDB(), c, result(recording_wav_base64=wav), TODAY)
    assert Path(c.recording_path) == tmp_path / "call_7.wav"
    c2 = call(o, status="dialing", id=8)
    c2.order = o
    rem.record_result(FakeDB(), c2, result(recording_wav_base64=base64.b64encode(b"not a wav").decode()), TODAY)
    assert c2.recording_path is None


def test_mark_handled():
    o = order()
    c = call(o, needs_followup=True)
    rem.mark_handled(FakeDB(), c, User(id=5, display_name="Asha", role="operator"), " verified UTR ")
    assert not c.needs_followup and c.handled_by == 5 and c.handled_note == "verified UTR"
    with pytest.raises(HTTPException):
        rem.mark_handled(FakeDB(), c, User(id=5, role="operator"), None)


def test_demo_mode_test_call_updates_order(monkeypatch):
    monkeypatch.setattr(get_settings(), "reminder_test_calls_apply", True)
    o = order()
    c = call(o, status="test", provider="browser")
    c.order = o
    rem.record_result(FakeDB(), c, result(intent="will_pay", promised_date="2026-10-24"), TODAY)
    assert c.status == "test" and o.payment_promised_date == date(2026, 10, 24)
    assert rem.attempts(o) == 0  # still not counted as a real attempt
