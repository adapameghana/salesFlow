"""Optional AI-assisted extraction using a locally running Ollama model.

Nothing is sent outside the machine: requests go to OLLAMA_URL (localhost).
The AI output is validated against the catalogue and branch list, gaps are
filled from the rules parser, and every AI order still needs operator review.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime

from ..config import get_settings
from .message_parser import BranchRef, ParsedItem, ParsedOrder, ProductRef, find_products, parse_message

log = logging.getLogger(__name__)

PROMPT = """You extract purchase orders from WhatsApp messages sent to a medical supplies distributor.
Today is {today}. Return ONLY JSON with this shape:
{{"customer_name": string|null, "delivery_location": string|null, "requested_date": "YYYY-MM-DD"|null,
  "contact_person": string|null, "items": [{{"product_code": string|null, "product_name": string, "quantity": number|null, "unit": string|null}}]}}

Rules:
- Use a product_code from the catalogue only when the product clearly matches; otherwise null.
- Never invent quantities, dates or locations. Use null when not stated.
- Resolve words like "tomorrow" or "friday" relative to today.

Product catalogue (code: name):
{catalogue}

Known branches: {branches}

Message from {sender}:
\"\"\"{message}\"\"\"
"""


def ollama_status() -> dict:
    settings = get_settings()
    if not settings.ai_enabled:
        return {"enabled": False, "available": False, "model": settings.ollama_model}
    try:
        with urllib.request.urlopen(f"{settings.ollama_url}/api/tags", timeout=3) as resp:
            models = [m["name"] for m in json.load(resp).get("models", [])]
        return {"enabled": True, "available": settings.ollama_model in models, "model": settings.ollama_model}
    except (urllib.error.URLError, OSError, ValueError):
        return {"enabled": True, "available": False, "model": settings.ollama_model}


def _call_ollama(prompt: str) -> dict:
    settings = get_settings()
    body = json.dumps({
        "model": settings.ollama_model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(f"{settings.ollama_url}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=settings.ollama_timeout_seconds) as resp:
        return json.loads(json.load(resp)["response"])


def _to_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_with_ai(
    text: str,
    received: datetime,
    catalogue: list[ProductRef],
    branches: list[BranchRef],
    sender_name: str | None = None,
    sender_reference: str | None = None,
) -> ParsedOrder:
    rules = parse_message(text, received, catalogue, branches, sender_name, sender_reference)
    try:
        data = _call_ollama(PROMPT.format(
            today=received.date().isoformat() + f" ({received:%A})",
            catalogue="\n".join(f"{p.code}: {p.name}" for p in catalogue),
            branches=", ".join(b.name for b in branches),
            sender=sender_name or "customer",
            message=text,
        ))
    except Exception as exc:  # AI is optional: fall back to rules
        log.warning("Local AI extraction failed: %s", exc)
        rules.flag("ai", "Local AI was unavailable, so rules-based extraction was used.")
        return rules

    result = ParsedOrder(method="ai", contact_reference=rules.contact_reference, notes=list(rules.notes))
    by_code = {p.code.upper(): p for p in catalogue}

    # Items: trust only catalogue codes; otherwise try to match the name with the rules matcher.
    for raw in data.get("items") or []:
        if not isinstance(raw, dict) or not raw.get("product_name") and not raw.get("product_code"):
            continue
        product = by_code.get(str(raw.get("product_code") or "").upper())
        if product is None:
            matched, _ = find_products(str(raw.get("product_name") or ""), catalogue)
            product = next((by_code[m.product_code] for m in matched), None)
        qty = _to_float(raw.get("quantity"))
        name = product.name if product else str(raw.get("product_name")).strip().title()
        result.items.append(ParsedItem(
            product_name=name, quantity=qty,
            unit=(product.unit if product else raw.get("unit")),
            product_id=product.id if product else None,
            product_code=product.code if product else None,
        ))
    if not result.items:
        result.items = rules.items
        if result.items:
            result.flag("ai", "AI found no items; items were taken from rules-based extraction.")

    result.customer_name = data.get("customer_name") or rules.customer_name

    location = data.get("delivery_location")
    branch = next((b for b in branches if location and b.name.lower() in str(location).lower()), None)
    if branch:
        result.delivery_address = branch.address or branch.name
    elif rules.delivery_address:
        result.delivery_address = rules.delivery_address
    elif location:
        result.delivery_address = str(location)
        result.flag("delivery_address", f"\"{location}\" is not a known branch - confirm the address.")

    try:
        result.requested_date = date.fromisoformat(data["requested_date"]) if data.get("requested_date") else None
    except (TypeError, ValueError):
        result.requested_date = None
    if rules.requested_date and result.requested_date != rules.requested_date:
        # Prefer the deterministic date resolver; the small model is weak at date arithmetic.
        result.requested_date = rules.requested_date

    if data.get("contact_person") and not any("Contact person" in n for n in result.notes):
        result.notes.append(f"Contact person: {data['contact_person']}")

    # Same validation flags as the rules parser
    if not result.items:
        result.flag("items", "No products could be identified in the message.")
    for item in result.items:
        if item.product_id is None:
            result.flag("items", f"\"{item.product_name}\" is not in the product catalogue.")
        if item.quantity is None:
            result.flag("items", f"Quantity missing for {item.product_name}.")
    if not result.customer_name:
        result.flag("customer_name", "Customer name not found.")
    if not result.delivery_address:
        result.flag("delivery_address", "Delivery location not found.")
    elif rules.delivery_address and not branch and any(f["field"] == "delivery_address" for f in rules.flags):
        result.flags.extend(f for f in rules.flags if f["field"] == "delivery_address")
    if not result.requested_date:
        result.flag("requested_date", "Requested delivery date not found.")
    elif result.requested_date < received.date():
        result.flag("requested_date", "Requested date is in the past.")
    return result
