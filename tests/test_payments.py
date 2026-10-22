"""Unit tests for prices, order totals and payment status (no database). Run:  python -m pytest tests"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.models import Order, OrderItem, OrderPayment, User  # noqa: E402
from app.schemas import PaymentIn  # noqa: E402
from app.services import payment_service as pay  # noqa: E402
from app.services.order_service import items_total, sync_amount_from_items  # noqa: E402

TODAY = date(2026, 10, 21)


class FakeDB:
    """Just enough of a Session for the payment service (audit rows are collected, not saved)."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def user(role="operator", department_id=None, uid=1):
    return User(id=uid, display_name=role, username=role, role=role, department_id=department_id)


def order(*lines, status="Assigned", department_id=3):
    o = Order(id=1, status=status, department_id=department_id, amount_paid=Decimal(0), payment_status="Unpaid")
    for qty, price in lines:
        o.items.append(OrderItem(product_name="x", quantity=Decimal(qty),
                                 unit_price=None if price is None else Decimal(price)))
    return o


def payment(amount, method="cash", paid_on=None, reference=None):
    return PaymentIn(amount=Decimal(str(amount)), method=method, paid_on=paid_on, reference=reference)


# ---------------------------------------------------------------- prices and totals

def test_line_total_and_items_total():
    o = order(("12", "650.00"), ("2", "1850.50"))
    assert o.items[0].line_total == Decimal("7800.00")
    assert items_total(o) == Decimal("11501.00")


def test_items_total_is_none_when_a_price_is_missing():
    assert items_total(order(("12", "650"), ("1", None))) is None


def test_amount_filled_from_items_but_manual_amount_kept_when_price_missing():
    o = order(("4", "25"))
    sync_amount_from_items(o)
    assert o.amount_due == Decimal("100.00") and o.payment_status == "Unpaid"

    o = order(("4", None))
    o.amount_due = Decimal("90")
    sync_amount_from_items(o)
    assert o.amount_due == Decimal("90")


# ---------------------------------------------------------------- payment status

def test_partial_then_full_payment():
    db, o, op = FakeDB(), order(("10", "100")), user()
    sync_amount_from_items(o)
    pay.record_payment(db, o, payment(400, "upi", reference="UTR123"), op, TODAY)
    assert (o.payment_status, o.amount_paid, pay.balance(o)) == ("Partially Paid", Decimal("400.00"), Decimal("600.00"))
    pay.record_payment(db, o, payment(600), op, TODAY)
    assert o.payment_status == "Paid" and pay.balance(o) == 0
    assert [a.action for a in db.added] == ["payment_recorded", "payment_recorded"]


def test_overpayment_future_date_and_missing_amount_are_refused():
    db, op = FakeDB(), user()
    o = order(("1", "100"))
    sync_amount_from_items(o)
    with pytest.raises(HTTPException) as err:
        pay.record_payment(db, o, payment(100.01), op, TODAY)
    assert err.value.status_code == 422
    with pytest.raises(HTTPException):
        pay.record_payment(db, o, payment(10, paid_on=date(2026, 10, 22)), op, TODAY)

    unpriced = order(("1", None))
    sync_amount_from_items(unpriced)
    with pytest.raises(HTTPException) as err:
        pay.record_payment(db, unpriced, payment(10), op, TODAY)
    assert "Set the order amount" in err.value.detail


def test_cancelled_order_takes_no_payment():
    o = order(("1", "100"), status="Cancelled")
    sync_amount_from_items(o)
    with pytest.raises(HTTPException):
        pay.record_payment(FakeDB(), o, payment(50), user(), TODAY)


def test_department_can_collect_only_for_its_own_orders():
    o = order(("1", "100"), department_id=3)
    sync_amount_from_items(o)
    assert pay.can_record_payment(user("department", department_id=3), o)
    assert not pay.can_record_payment(user("department", department_id=4), o)
    assert not pay.can_set_amount(user("department", department_id=3), o)


def test_amount_cannot_go_below_money_received():
    db, op = FakeDB(), user()
    o = order(("1", "100"))
    sync_amount_from_items(o)
    pay.record_payment(db, o, payment(80), op, TODAY)
    with pytest.raises(HTTPException):
        pay.set_amount_due(db, o, Decimal("50"), op)
    pay.set_amount_due(db, o, Decimal("80"), op)  # e.g. a discount
    assert o.payment_status == "Paid"


def test_only_managers_remove_payments_and_status_recalculates():
    db = FakeDB()
    o = order(("1", "100"))
    sync_amount_from_items(o)
    o.payments.append(OrderPayment(id=7, amount=Decimal("100"), method="cash", paid_on=TODAY))
    pay.refresh_payment_state(o)
    assert o.payment_status == "Paid"
    with pytest.raises(HTTPException) as err:
        pay.remove_payment(db, o, 7, "wrong order", user("operator"))
    assert err.value.status_code == 403
    pay.remove_payment(db, o, 7, "wrong order", user("supervisor"))
    assert o.payment_status == "Unpaid" and o.amount_paid == 0


def test_free_order_counts_as_paid():
    o = order(("1", "0"))
    sync_amount_from_items(o)
    assert o.payment_status == "Paid"
