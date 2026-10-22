"""Payment tracking: the amount an order costs, the payments received against it, and whether it is paid.

No payment is taken here. Staff record money the customer has already paid (cash, UPI, bank
transfer...). Only a reference number is kept, never card numbers or bank login details.
"""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Order, OrderPayment, User
from ..security import MANAGERS, OFFICE
from .audit import audit

PAYMENT_STATUSES = ["Unpaid", "Partially Paid", "Paid"]
METHOD_LABELS = {
    "cash": "Cash", "upi": "UPI", "bank_transfer": "Bank transfer",
    "card": "Card", "cheque": "Cheque", "other": "Other",
}
ZERO = Decimal("0.00")


def paise(value: Decimal | None) -> Decimal | None:
    """Round to 2 decimals, as the database stores it."""
    return None if value is None else value.quantize(Decimal("0.01"))


def money(value: Decimal | None) -> str:
    return f"{(value or ZERO):,.2f}"


def balance(order: Order) -> Decimal | None:
    if order.amount_due is None:
        return None
    return order.amount_due - (order.amount_paid or ZERO)


def refresh_payment_state(order: Order) -> None:
    """Recalculate amount_paid and payment_status from the payment rows."""
    paid = sum((p.amount for p in order.payments), ZERO)
    order.amount_paid = paid
    if order.amount_due is not None and paid >= order.amount_due and (paid > 0 or order.amount_due == 0):
        order.payment_status = "Paid"
    elif paid > 0:
        order.payment_status = "Partially Paid"
    else:
        order.payment_status = "Unpaid"


# ---------------------------------------------------------------- permissions

def can_set_amount(user: User, order: Order) -> bool:
    return user.role in OFFICE and order.status != "Cancelled"


def can_record_payment(user: User, order: Order) -> bool:
    """Office staff, plus the department handling the order (e.g. dispatch collecting cash on delivery)."""
    if order.status == "Cancelled" or order.amount_due is None:
        return False
    return user.role in OFFICE or order.department_id == user.department_id


def can_remove_payment(user: User) -> bool:
    return user.role in MANAGERS


# ---------------------------------------------------------------- actions

def set_amount_due(db: Session, order: Order, amount: Decimal | None, user: User) -> None:
    if not can_set_amount(user, order):
        raise HTTPException(403 if user.role not in OFFICE else 400,
                            "Only office users can set the amount, and not on a cancelled order")
    amount = paise(amount)
    if amount is None and order.payments:
        raise HTTPException(422, "Payments are already recorded - the amount cannot be cleared")
    if amount is not None and amount < (order.amount_paid or ZERO):
        raise HTTPException(422, f"Amount cannot be less than what was already received ({money(order.amount_paid)})")
    old = order.amount_due
    order.amount_due = amount
    refresh_payment_state(order)
    audit(db, user, "amount_due_set", "order", order.id,
          f"{money(old) if old is not None else 'not set'} -> {money(amount) if amount is not None else 'not set'}")


def record_payment(db: Session, order: Order, data, user: User, today: date) -> OrderPayment:
    if order.status == "Cancelled":
        raise HTTPException(400, "Cannot record a payment on a cancelled order")
    if order.amount_due is None:
        raise HTTPException(422, "Set the order amount before recording a payment")
    if not can_record_payment(user, order):
        raise HTTPException(403, "You cannot record payments for this order")
    paid_on = data.paid_on or today
    if paid_on > today:
        raise HTTPException(422, "Payment date cannot be in the future")
    amount = paise(data.amount)
    remaining = balance(order)
    if amount <= 0:
        raise HTTPException(422, "Payment amount must be more than zero")
    if amount > remaining:
        raise HTTPException(422, f"Payment is more than the balance due ({money(remaining)})")
    payment = OrderPayment(
        amount=amount, method=data.method,
        reference=(data.reference or "").strip() or None,
        paid_on=paid_on, note=(data.note or "").strip() or None,
        recorded_by=user.id,
    )
    order.payments.append(payment)
    refresh_payment_state(order)
    db.flush()
    audit(db, user, "payment_recorded", "order", order.id,
          f"{money(amount)} by {METHOD_LABELS[data.method]}"
          + (f" ref {payment.reference}" if payment.reference else "")
          + f" - now {order.payment_status}")
    return payment


def remove_payment(db: Session, order: Order, payment_id: int, reason: str, user: User) -> None:
    """For payments entered by mistake. Managers only; the audit log keeps what was removed."""
    if not can_remove_payment(user):
        raise HTTPException(403, "Only a supervisor or admin can remove a payment")
    payment = next((p for p in order.payments if p.id == payment_id), None)
    if payment is None:
        raise HTTPException(404, "Payment not found on this order")
    order.payments.remove(payment)
    refresh_payment_state(order)
    audit(db, user, "payment_removed", "order", order.id,
          f"{money(payment.amount)} by {METHOD_LABELS.get(payment.method, payment.method)} on {payment.paid_on}"
          f" removed: {reason.strip()} - now {order.payment_status}")


# ---------------------------------------------------------------- serialization

def _num(value: Decimal | None):
    return None if value is None else float(value)


def payment_summary(order: Order) -> dict:
    return {
        "payment_status": order.payment_status,
        "amount_due": _num(order.amount_due),
        "amount_paid": _num(order.amount_paid or ZERO),
        "balance": _num(balance(order)),
    }


def payment_detail(order: Order, user: User) -> dict:
    return {
        "payments": [{
            "id": p.id, "amount": _num(p.amount), "method": p.method,
            "method_label": METHOD_LABELS.get(p.method, p.method),
            "reference": p.reference, "paid_on": p.paid_on, "note": p.note,
            "recorded_by": p.user.display_name if p.user else "System", "created_at": p.created_at,
        } for p in order.payments],
        "can_set_amount": can_set_amount(user, order),
        "can_record_payment": can_record_payment(user, order),
        "can_remove_payment": can_remove_payment(user),
    }
