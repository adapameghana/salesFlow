"""Utterance classification with a local Ollama model, with keyword fallback.

The LLM never writes what the agent says. It only labels the customer's reply as
JSON {intent, promised_date, paid_method, note}, which is validated here.
Uses the same Ollama call pattern as backend/app/services/ai_parser.py.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date, timedelta

from .heuristics import classify_heuristic, find_date, find_paid_method
from .models import INTENTS, PAID_METHODS, CallContext, Classification

log = logging.getLogger(__name__)

LANG_NAMES = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil"}
QUESTIONS = {
    "payment_answer": "When will you be able to make the payment?",
    "paid_details": "How and when did you make the payment?",
    "date": "On which date will you be able to pay?",
}
MAX_PROMISE_DAYS = 120  # a "promise" further out than this is treated as no date

PROMPT = """You label a customer's spoken reply during a polite payment reminder phone call
from a medical supplies distributor. The reply was transcribed from {language} speech and may
mix English words or contain transcription errors.

Today is {today} ({weekday}). Pending amount: Rs {balance}. Order: {order_number}.
The agent just asked: "{question}"

Return ONLY JSON with this shape:
{{"intent": "paid_claimed"|"will_pay"|"ask_details"|"callback"|"dispute"|"wrong_number"|"not_interested"|"other",
  "promised_date": "YYYY-MM-DD"|null,
  "paid_method": "UPI"|"cash"|"cheque"|"bank transfer"|"card"|"online"|null,
  "note": "short English paraphrase of what the customer said"}}

Intent meanings:
- paid_claimed: says they already paid / transferred / sent the money.
- will_pay: says they will pay (with or without a date).
- ask_details: asks which order, how much, what items, or who is calling.
- callback: busy now, asks to be called later.
- dispute: says the amount/bill is wrong, goods not received/damaged/returned, or did not order.
- wrong_number: says this is the wrong person or number.
- not_interested: asks not to be called again.
- other: anything else, unclear or empty.

Rules:
- promised_date is ONLY for will_pay: the date they will pay by. Never guess; null if not stated.
- Resolve relative dates from today: tomorrow / kal (कल) / repu (రేపు) / naalai (நாளை) = today + 1;
  parso (परसों) / ellundi (ఎల్లుండి) / naalai marunaal = today + 2; a weekday name = the next such day
  after today; "next week" = today + 7; "month end" = the last day of this month.
- paid_method only if they name it.

Customer said:
\"\"\"{text}\"\"\"
"""


def _call_ollama(url: str, model: str, prompt: str, timeout: float) -> dict:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
        "keep_alive": "60m",  # stay loaded between calls; reloading costs 5-10 s on a CPU
    }).encode()
    req = urllib.request.Request(f"{url}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(json.load(resp)["response"])


def ollama_reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def validate_llm_output(data: object, text: str, ctx: CallContext) -> Classification | None:
    """Turn raw LLM JSON into a Classification, or None if it is unusable."""
    if not isinstance(data, dict):
        return None
    intent = str(data.get("intent") or "").strip().lower()
    if intent not in INTENTS:
        return None
    promised: date | None = None
    raw_date = data.get("promised_date")
    if intent == "will_pay" and raw_date:
        try:
            promised = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            promised = None
        if promised and not (ctx.today <= promised <= ctx.today + timedelta(days=MAX_PROMISE_DAYS)):
            promised = None
    method = data.get("paid_method")
    method = next((m for m in PAID_METHODS if isinstance(method, str) and m.lower() == method.lower()),
                  None)
    note = str(data.get("note") or "").strip()[:200] or text.strip()[:200]
    return Classification(intent=intent, promised_date=promised, paid_method=method, note=note,
                          source="llm")


class OllamaClassifier:
    """Classifier backed by Ollama; falls back to keyword heuristics on any failure."""

    def __init__(self, url: str, model: str, timeout: float = 20.0, enabled: bool = True):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.enabled = enabled

    def __call__(self, text: str, ctx: CallContext, expecting: str) -> Classification:
        fallback = classify_heuristic(text, ctx.language, ctx.today, expecting)
        if not self.enabled or not text.strip():
            return fallback
        prompt = PROMPT.format(
            language=LANG_NAMES.get(ctx.language, "English"),
            today=ctx.today.isoformat(), weekday=ctx.today.strftime("%A"),
            balance=f"{ctx.balance:.0f}", order_number=ctx.order_number,
            question=QUESTIONS.get(expecting, QUESTIONS["payment_answer"]), text=text.strip(),
        )
        try:
            result = validate_llm_output(_call_ollama(self.url, self.model, prompt, self.timeout),
                                         text, ctx)
        except Exception as exc:  # Ollama is optional: keywords keep the call going
            log.warning("Ollama classification failed, using keywords: %s", exc)
            return fallback
        if result is None:
            log.warning("Ollama returned invalid output, using keywords")
            return fallback
        # Small models get calendar maths wrong ("Friday" -> the wrong day), so a date the
        # deterministic parser can read always wins; the model's date is only a fallback.
        if result.intent == "will_pay":
            result.promised_date = find_date(text, ctx.today) or result.promised_date
        if result.paid_method is None:
            result.paid_method = find_paid_method(text)
        if expecting == "paid_details" and result.intent in ("other", "will_pay"):
            result.intent, result.promised_date = "paid_claimed", None
        return result
