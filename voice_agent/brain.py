"""Conversation state machine for a payment reminder call.

Pure logic: it takes customer text (or silence/timeout/hangup events) and returns
what the agent should say next. Speech, audio and timing live in pipeline.py.

    greet -> MAIN --paid_claimed--> PAID_DETAILS -> thank, end
                  --will_pay + date--> confirm, end
                  --will_pay, no date--> DATE -> confirm / "pay soon", end
                  --ask_details--> repeat amount + items, ask again (stay in MAIN)
                  --callback/dispute--> "team will call you back", end
                  --other--> ask once more, then "team will call you back", end
                  --wrong_number/not_interested--> apologise, end
    silence: reprompt once, then close with no_response.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .models import CallContext, Classification, Classifier
from .numwords import digits_to_words, number_to_words, quantity_to_words, rupees_to_words, when_to_words
from .phrases import render

MAX_ITEMS_SPOKEN = 4


class State(str, Enum):
    START = "start"
    MAIN = "main"  # waiting for "when will you pay"
    PAID_DETAILS = "paid_details"  # waiting for "how/when did you pay"
    DATE = "date"  # waiting for a payment date
    ENDED = "ended"


@dataclass
class Reply:
    text: str
    end: bool = False
    interruptible: bool = True  # the closing message is always played to the end


@dataclass
class Outcome:
    intent: str | None
    promised_date: date | None
    paid_method: str | None
    summary: str
    notes: list[str] = field(default_factory=list)


def spoken_order_number(order_number: str, lang: str) -> str:
    """'ORD-2026-0007' -> 'seven': the last group of digits, read digit by digit."""
    groups = re.findall(r"\d+", order_number or "")
    if not groups:
        return order_number or ""
    digits = groups[-1].lstrip("0") or "0"
    return digits_to_words(digits, lang)


# Spoken forms of common pack sizes; anything else is read as written.
_UNIT_WORDS = {"ml": "ml", "mg": "milligram", "g": "gram", "gm": "gram", "kg": "kilogram", "l": "litre"}
_ES_PLURAL = ("box", "pouch", "patch", "inch")


def _plural_unit(unit: str, qty: float | None) -> str:
    if qty is None or qty == 1 or unit.endswith("s"):
        return unit
    return unit + ("es" if unit.lower() in _ES_PLURAL else "s")


def spoken_product(name: str, lang: str) -> str:
    """'Insulin Vial 10ml' -> 'Insulin Vial ten ml': TTS reads pack sizes glued to units badly."""
    def pack(m: re.Match) -> str:
        unit = m.group(2)
        return f"{number_to_words(int(m.group(1)), lang)} {_UNIT_WORDS.get(unit.lower(), unit)}"
    return re.sub(r"\b(\d+)\s*(ml|mg|gm|g|kg|l)\b", pack, name, flags=re.IGNORECASE)


def spoken_items(ctx: CallContext) -> str:
    lang = ctx.language
    parts = []
    for item in ctx.items[:MAX_ITEMS_SPOKEN]:
        bits = []
        if item.quantity is not None:
            bits.append(quantity_to_words(item.quantity, lang))
        # English units only make sense in English, and "ten vial Insulin Vial" repeats itself.
        if item.unit and lang == "en" and item.unit.lower() not in item.name.lower():
            bits.append(_plural_unit(item.unit, item.quantity))
        bits.append(spoken_product(item.name, lang))
        parts.append(" ".join(bits))
    if len(ctx.items) > MAX_ITEMS_SPOKEN:
        parts.append(render("more_items", lang))
    if not parts:
        return render("more_items", lang)
    conj = render("and", lang)
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} {conj} {parts[-1]}"


def _tidy(text: str, lang: str = "") -> str:
    text = re.sub(r"\s+([,.?!।])", r"\1", " ".join(text.split()))
    if lang == "en":  # "four thousand rupees is still pending" may start a sentence
        text = re.sub(r"(^|[.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text


class Brain:
    def __init__(self, ctx: CallContext, classifier: Classifier, max_turns: int = 4):
        self.ctx = ctx
        self.lang = ctx.language
        self.classify = classifier
        self.max_turns = max_turns
        self.state = State.START
        self.turns = 0
        self.silences = 0  # consecutive
        self.unclear = 0
        self.intent: str | None = None
        self.promised_date: date | None = None
        self.paid_method: str | None = None
        self.notes: list[str] = []
        self.hung_up = False
        self.timed_out = False

    # ------------------------------------------------------------ helpers
    @property
    def done(self) -> bool:
        return self.state == State.ENDED

    def _amount(self) -> str:
        return rupees_to_words(self.ctx.balance, self.lang)

    def _say(self, key: str, **values: str) -> str:
        return render(key, self.lang, **values)

    def _end(self, key: str, **values: str) -> Reply:
        self.state = State.ENDED
        return Reply(_tidy(f"{self._say(key, **values)} {self._say('goodbye')}", self.lang), end=True,
                     interruptible=False)

    # ------------------------------------------------------------ events
    def greeting(self) -> Reply:
        self.state = State.MAIN
        name = self.ctx.customer_name
        text = self._say("greet", name=name, business=self.ctx.business_name or "",
                         order=spoken_order_number(self.ctx.order_number, self.lang),
                         amount=self._amount())
        if not name:  # avoid "Hello , ..." / "నమస్కారం గారు"
            text = text.replace(" గారు", "").replace("Hello ,", "Hello,")
        return Reply(_tidy(text, self.lang))

    def on_customer(self, text: str) -> Reply:
        if self.done:
            return Reply("", end=True)
        if not text.strip():
            return self.on_silence()
        self.turns += 1
        self.silences = 0
        expecting = {State.PAID_DETAILS: "paid_details", State.DATE: "date"}.get(
            self.state, "payment_answer")
        c = self.classify(text, self.ctx, expecting)
        if c.note:
            self.notes.append(c.note)
        if c.paid_method:
            self.paid_method = c.paid_method
        if self.state == State.PAID_DETAILS:
            reply = self._on_paid_details(c)
        elif self.state == State.DATE:
            reply = self._on_date(c)
        else:
            reply = self._on_main(c)
        if not reply.end and self.turns >= self.max_turns:
            # Keep calls short: wrap up politely with what we know.
            if self.intent == "will_pay":
                return self._end("will_pay_no_date")
            self.intent = self.intent or "other"
            return self._end("callback")
        return reply

    def on_silence(self) -> Reply:
        if self.done:
            return Reply("", end=True)
        self.silences += 1
        if self.state == State.PAID_DETAILS:
            return self._end("paid_thanks")
        if self.state == State.DATE:
            return self._end("will_pay_no_date")
        if self.silences >= 2:
            self.intent = self.intent or "no_response"
            return self._end("no_response")
        return Reply(self._say("reprompt"))

    def on_timeout(self) -> Reply:
        """The hard call-length cap was reached."""
        if self.done:
            return Reply("", end=True)
        self.timed_out = True
        self.intent = self.intent or ("other" if self.turns else "no_response")
        return self._end("time_up")

    def on_hangup(self) -> None:
        if not self.done:
            self.hung_up = True
            self.intent = self.intent or ("other" if self.turns else "no_response")
            self.state = State.ENDED

    # ------------------------------------------------------------ handlers
    def _on_main(self, c: Classification) -> Reply:
        if c.intent == "paid_claimed":
            self.intent = "paid_claimed"
            if c.paid_method:  # they already told us how
                return self._end("paid_thanks")
            self.state = State.PAID_DETAILS
            return Reply(self._say("ask_paid_how"))
        if c.intent == "will_pay":
            self.intent = "will_pay"
            if c.promised_date:
                return self._confirm_date(c.promised_date)
            self.state = State.DATE
            return Reply(self._say("ask_date"))
        if c.intent == "ask_details":
            self.intent = "ask_details"
            self.state = State.MAIN
            details = self._say("details", order=spoken_order_number(self.ctx.order_number, self.lang),
                                items=spoken_items(self.ctx), amount=self._amount())
            return Reply(_tidy(f"{details} {self._say('ask_when')}", self.lang))
        if c.intent in ("callback", "dispute"):
            self.intent = c.intent
            return self._end("callback")
        if c.intent in ("wrong_number", "not_interested"):
            self.intent = c.intent
            return self._end(c.intent)
        # other: give the customer one more chance before handing over to the team
        self.unclear += 1
        if self.unclear >= 2:
            self.intent = "other" if self.intent in (None, "ask_details") else self.intent
            return self._end("callback")
        return Reply(self._say("not_understood"))

    def _on_paid_details(self, c: Classification) -> Reply:
        if c.intent in ("dispute", "wrong_number", "not_interested", "callback"):
            return self._on_main(c)
        return self._end("paid_thanks")

    def _on_date(self, c: Classification) -> Reply:
        if c.promised_date:
            self.intent = "will_pay"
            return self._confirm_date(c.promised_date)
        if c.intent in ("paid_claimed", "dispute", "wrong_number", "not_interested", "callback",
                        "ask_details"):
            return self._on_main(c)
        return self._end("will_pay_no_date")

    def _confirm_date(self, when: date) -> Reply:
        self.promised_date = when
        return self._end("will_pay_confirm", when=when_to_words(when, self.ctx.today, self.lang))

    # ------------------------------------------------------------ result
    def outcome(self) -> Outcome:
        return Outcome(intent=self.intent, promised_date=self.promised_date,
                       paid_method=self.paid_method, summary=self.summary(), notes=list(self.notes))

    def summary(self) -> str:
        via = f" via {self.paid_method}" if self.paid_method else ""
        last_note = (self.notes[-1] if self.notes else "").strip().rstrip(".!?।")
        said = f' Customer said: "{last_note}".' if last_note else ""
        i = self.intent
        if i == "paid_claimed":
            s = f"Customer says the payment was already made{via}. Staff should verify it."
        elif i == "will_pay" and self.promised_date:
            s = f"Customer will pay on {self.promised_date.isoformat()} ({self.promised_date:%A}){via}."
        elif i == "will_pay":
            s = f"Customer will pay{via} but did not give a date."
        elif i == "ask_details":
            s = "Customer asked for the order details; no payment date was given."
        elif i == "callback":
            s = "Customer asked to be called back."
        elif i == "dispute":
            s = "Customer disputes the order or amount; the team should follow up."
        elif i == "wrong_number":
            s = "Wrong number; reminders should stop."
        elif i == "not_interested":
            s = "Customer asked not to be called again."
        elif i == "no_response":
            s = "No response from the customer."
        else:
            s = "Customer's reply was unclear; the team should call back."
        if i not in (None, "no_response", "will_pay") or (i == "will_pay" and not self.promised_date):
            s += said
        if self.hung_up:
            s += " Customer hung up."
        if self.timed_out:
            s += " Call reached the time limit."
        return s
