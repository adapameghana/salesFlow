"""Rules-based extraction of order fields from free-text WhatsApp messages.

The parser never silently guesses high-impact details: anything missing or
uncertain is returned as a review flag so an operator must confirm it.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100,
}

UNIT_WORDS = {
    "box": "box", "boxes": "box", "bx": "box",
    "strip": "strip", "strips": "strip",
    "bottle": "bottle", "bottles": "bottle", "btl": "bottle",
    "unit": "unit", "units": "unit", "pc": "unit", "pcs": "unit", "piece": "unit",
    "pieces": "unit", "nos": "unit", "no": "unit", "no.": "unit",
    "pack": "pack", "packs": "pack", "packet": "pack", "packets": "pack",
    "vial": "vial", "vials": "vial",
    "carton": "carton", "cartons": "carton",
    "dozen": "dozen",
}

NUMBER_RE = r"(\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUMBERS, key=len, reverse=True)) + r")"
UNIT_RE = r"(" + "|".join(re.escape(u) for u in sorted(UNIT_WORDS, key=len, reverse=True)) + r")"

# "12 boxes of", "12 x", "12"
QTY_BEFORE_RE = re.compile(r"(?<![A-Za-z0-9])" + NUMBER_RE + r"\s*(?:" + UNIT_RE + r"\b)?\s*(?:of\s+|x\s+|-\s*)?(?:the\s+)?$", re.I)
# "gloves - 12 boxes", "gloves x 12", "gloves: 12"
QTY_AFTER_RE = re.compile(r"^\s*(?:[-:x×*]|qty)?\s*" + NUMBER_RE + r"\s*(?:" + UNIT_RE + r"\b)?", re.I)
# Item-looking phrases that did not match the catalogue: "5 boxes of xyz"
UNKNOWN_ITEM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*" + UNIT_RE + r"\s+(?:of\s+)?([a-z][a-z0-9\- ]{2,40}?)(?=\s+(?:and|to|for|by|on|at|tomorrow|today)\b|[,.;\n]|$)",
    re.I,
)

PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
CONTACT_RE = re.compile(r"\b(?i:contact|call|reach|ask for)\s+(?i:mr\.?\s+|ms\.?\s+|dr\.?\s+)?([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)")
CUSTOMER_RE = re.compile(
    r"\b(?:this is|from|for)\s+(?:the\s+)?([A-Z][\w&.']*(?:\s+[A-Z][\w&.']*)*\s+"
    r"(?:Hospital|Hospitals|Clinic|Pharmacy|Medicals|Medical Stores|Medical|Labs|Lab|Diagnostics|Nursing Home))\b"
)
LOCATION_RE = re.compile(
    r"\b(?:deliver(?:ed|y)?\s+(?:it\s+|them\s+)?(?:to|at)|send\s+(?:it\s+|them\s+)?to|to|at)\s+(?:the\s+|our\s+)?"
    r"([A-Z][A-Za-z0-9.'-]*(?:\s+[A-Z][A-Za-z0-9.'-]*)*(?:\s+(?:branch|hospital|clinic|office|store|warehouse))?)"
)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass
class ProductRef:
    id: int
    code: str
    name: str
    unit: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class BranchRef:
    id: int
    name: str
    address: str | None


@dataclass
class ParsedItem:
    product_name: str
    quantity: float | None
    unit: str | None
    product_id: int | None = None
    product_code: str | None = None


@dataclass
class ParsedOrder:
    customer_name: str | None = None
    contact_reference: str | None = None
    delivery_address: str | None = None
    requested_date: date | None = None
    items: list[ParsedItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)
    method: str = "rules"

    def flag(self, field_name: str, message: str) -> None:
        self.flags.append({"field": field_name, "message": message})


def to_number(token: str) -> float | None:
    token = token.lower()
    if token in WORD_NUMBERS:
        return float(WORD_NUMBERS[token])
    try:
        return float(token)
    except ValueError:
        return None


def normalise_unit(unit: str | None) -> str | None:
    return UNIT_WORDS.get(unit.lower()) if unit else None


def find_products(text: str, catalogue: list[ProductRef]) -> tuple[list[ParsedItem], list[tuple[int, int]]]:
    """Find catalogue products mentioned in the text and the quantity next to each."""
    lowered = text.lower()
    candidates: list[tuple[str, ProductRef]] = []
    for product in catalogue:
        for term in {product.name.lower(), product.code.lower(), *product.aliases}:
            if term not in UNIT_WORDS:  # a bare unit word ("strips") is not a product
                candidates.append((term, product))
    candidates.sort(key=lambda c: len(c[0]), reverse=True)  # longest phrase wins

    taken: list[tuple[int, int]] = []
    hits: list[tuple[int, ParsedItem]] = []
    seen_products: set[int] = set()
    for term, product in candidates:
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(term) + r"(?:s|es)?(?![a-z0-9])", lowered):
            start, end = m.span()
            if any(start < e and end > s for s, e in taken):
                continue
            taken.append((start, end))
            if product.id in seen_products:
                continue
            seen_products.add(product.id)

            qty, unit = None, None
            before = QTY_BEFORE_RE.search(text[max(0, start - 30):start])
            after = QTY_AFTER_RE.match(text[end:end + 25])
            if before:
                qty, unit = to_number(before.group(1)), normalise_unit(before.group(2))
            elif after:
                qty, unit = to_number(after.group(1)), normalise_unit(after.group(2))
            if unit == "dozen" and qty is not None:
                qty, unit = qty * 12, None
            hits.append((start, ParsedItem(
                product_name=product.name, quantity=qty, unit=unit or product.unit,
                product_id=product.id, product_code=product.code,
            )))
    hits.sort(key=lambda h: h[0])
    return [item for _, item in hits], taken


def find_unknown_items(text: str, taken: list[tuple[int, int]]) -> list[ParsedItem]:
    items = []
    for m in UNKNOWN_ITEM_RE.finditer(text):
        s, e = m.span()
        if any(s < te and e > ts for ts, te in taken):
            continue
        items.append(ParsedItem(
            product_name=m.group(3).strip().title(), quantity=to_number(m.group(1)),
            unit=normalise_unit(m.group(2)),
        ))
    return items


def parse_date(text: str, received: datetime) -> tuple[date | None, str | None]:
    """Resolve the requested delivery date. Returns (date, note)."""
    lowered = text.lower()
    today = received.date()

    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", lowered)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d), None
        except ValueError:
            pass

    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\b", lowered) or \
        re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", lowered)
    if m:
        a, b = m.group(1), m.group(2)
        day, mon = (int(a), MONTHS[b[:3]]) if a.isdigit() else (int(b), MONTHS[a[:3]])
        try:
            resolved = date(today.year, mon, day)
            if resolved < today - timedelta(days=30):
                resolved = date(today.year + 1, mon, day)
            return resolved, None
        except ValueError:
            pass

    if "day after tomorrow" in lowered:
        return today + timedelta(days=2), None
    if re.search(r"\b(tomorrow|tmrw|tmr|tomorow)\b", lowered):
        return today + timedelta(days=1), None
    if re.search(r"\b(today|tonight|this evening|asap|immediately|urgent(?:ly)?|emergency)\b", lowered):
        return today, "Marked urgent / same day"
    m = re.search(r"\bnext week\b", lowered)
    if m:
        return today + timedelta(days=7 - today.weekday()), "\"next week\" resolved to next Monday"
    for idx, name in enumerate(WEEKDAYS):
        if re.search(r"\b" + name + r"\b", lowered):
            delta = (idx - today.weekday()) % 7 or 7
            return today + timedelta(days=delta), None
    m = re.search(r"\b(?:in|within)\s+" + NUMBER_RE + r"\s+days?\b", lowered)
    if m:
        n = to_number(m.group(1))
        if n:
            return today + timedelta(days=int(n)), None
    return None, None


def find_location(text: str, branches: list[BranchRef]) -> tuple[str | None, bool]:
    """Return (address, is_known_branch)."""
    lowered = text.lower()
    for branch in sorted(branches, key=lambda b: len(b.name), reverse=True):
        if re.search(r"\b" + re.escape(branch.name.lower()) + r"\b", lowered):
            return branch.address or branch.name, True
    m = LOCATION_RE.search(text)
    if m:
        place = m.group(1).strip(" .,")
        if place.lower() not in {"i", "we", "please", "sir", "madam"} and len(place) > 2:
            return place, False
    return None, False


def parse_message(
    text: str,
    received: datetime,
    catalogue: list[ProductRef],
    branches: list[BranchRef],
    sender_name: str | None = None,
    sender_reference: str | None = None,
) -> ParsedOrder:
    result = ParsedOrder()
    clean = " ".join(text.split())

    # Items
    items, taken = find_products(clean, catalogue)
    unknown = find_unknown_items(clean, taken)
    result.items = items + unknown
    if not result.items:
        result.flag("items", "No products could be identified in the message.")
    for item in result.items:
        if item.product_id is None:
            result.flag("items", f"\"{item.product_name}\" is not in the product catalogue.")
        if item.quantity is None:
            result.flag("items", f"Quantity missing for {item.product_name}.")

    # Customer
    m = CUSTOMER_RE.search(clean)
    if m:
        result.customer_name = m.group(1).strip()
    elif sender_name:
        result.customer_name = sender_name
    else:
        result.flag("customer_name", "Customer name not found.")

    # Contact
    phone = PHONE_RE.search(clean)
    contact = CONTACT_RE.search(clean)
    if phone:
        result.contact_reference = re.sub(r"[\s-]", "", phone.group(1))
    elif sender_reference:
        result.contact_reference = sender_reference
    if contact:
        result.notes.append(f"Contact person: {contact.group(1)}" + (" (no phone number given)" if not phone else ""))

    # Delivery location
    address, known = find_location(clean, branches)
    result.delivery_address = address
    if not address:
        result.flag("delivery_address", "Delivery location not found.")
    elif not known:
        result.flag("delivery_address", f"\"{address}\" is not a known branch - confirm the address.")

    # Date
    requested, note = parse_date(clean, received)
    result.requested_date = requested
    if note:
        result.notes.append(note)
    if not requested:
        result.flag("requested_date", "Requested delivery date not found.")
    elif requested < received.date():
        result.flag("requested_date", "Requested date is in the past.")

    return result
