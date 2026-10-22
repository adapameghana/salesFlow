"""Shared data types: the call context from the backend and classifier output."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from .phrases import normalize_lang

# Intents the classifier may return for one customer utterance.
INTENTS = ("paid_claimed", "will_pay", "ask_details", "callback", "dispute",
           "wrong_number", "not_interested", "other")
# Final call intents (contract): the above plus no_response.
CALL_INTENTS = INTENTS + ("no_response",)
PAID_METHODS = ("UPI", "cash", "cheque", "bank transfer", "card", "online")
CALL_STATUSES = ("answered", "no_answer", "busy", "failed")


@dataclass
class OrderItem:
    name: str
    quantity: float | None = None
    unit: str | None = None


@dataclass
class CallContext:
    """The `context` object of the interface contract."""
    order_id: int | None
    order_number: str
    customer_name: str
    language: str
    balance: float
    business_name: str
    today: date
    amount_due: float | None = None
    amount_paid: float | None = None
    attempt_no: int = 1
    items: list[OrderItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CallContext":
        today = data.get("today")
        try:
            today_d = date.fromisoformat(str(today)) if today else date.today()
        except ValueError:
            today_d = date.today()
        items = []
        for raw in data.get("items") or []:
            if isinstance(raw, dict) and raw.get("name"):
                qty = raw.get("quantity")
                try:
                    qty = float(qty) if qty is not None else None
                except (TypeError, ValueError):
                    qty = None
                items.append(OrderItem(str(raw["name"]), qty, raw.get("unit") or None))
        return cls(
            order_id=data.get("order_id"),
            order_number=str(data.get("order_number") or ""),
            customer_name=str(data.get("customer_name") or "").strip(),
            language=normalize_lang(data.get("language")),
            balance=float(data.get("balance") or 0),
            business_name=str(data.get("business_name") or "").strip(),
            today=today_d,
            amount_due=data.get("amount_due"),
            amount_paid=data.get("amount_paid"),
            attempt_no=int(data.get("attempt_no") or 1),
            items=items,
        )


@dataclass
class Classification:
    intent: str = "other"
    promised_date: date | None = None
    paid_method: str | None = None
    note: str = ""
    source: str = "heuristic"  # heuristic | llm


class Classifier(Protocol):
    """Classifies one customer utterance. `expecting` says what the agent just asked:
    'payment_answer' (when will you pay), 'paid_details' (how/when did you pay) or 'date'."""

    def __call__(self, text: str, ctx: CallContext, expecting: str) -> Classification: ...


@dataclass
class TranscriptEntry:
    speaker: str  # agent | customer
    text: str
    ts: float  # seconds since the call was answered

    def as_dict(self) -> dict[str, Any]:
        return {"speaker": self.speaker, "text": self.text, "ts": round(self.ts, 2)}
