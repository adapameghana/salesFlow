"""Unit tests for the rules-based parser. Run from the project root:  python -m pytest tests"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.message_parser import BranchRef, ProductRef, parse_message  # noqa: E402

IST = timezone(timedelta(minutes=330))
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=IST)  # a Monday

CATALOGUE = [
    ProductRef(1, "PH-PCM500", "Paracetamol 500mg Tablets", "strip", ["paracetamol", "pcm", "dolo", "crocin"]),
    ProductRef(4, "PH-CSY100", "Cough Syrup 100ml", "bottle", ["cough syrup", "syrup"]),
    ProductRef(6, "SS-GLV-M", "Surgical Gloves (Medium)", "box", ["gloves", "surgical gloves"]),
    ProductRef(7, "SS-N95", "N95 Face Masks", "box", ["n95 masks", "n95 mask", "n95", "masks", "mask"]),
    ProductRef(10, "ME-BPM", "Digital BP Monitor", "unit", ["bp monitor", "bp machine"]),
    ProductRef(11, "ME-GLU", "Glucometer Kit", "unit", ["glucometer"]),
    ProductRef(12, "ME-GSTR", "Glucometer Test Strips (50)", "box", ["test strips", "glucometer strips"]),
]
BRANCHES = [BranchRef(1, "Vijayawada", "Vijayawada branch, MG Road"), BranchRef(2, "Guntur", "Guntur branch")]


def parse(text, sender_name="WhatsApp Sender", **kw):
    return parse_message(text, NOW, CATALOGUE, BRANCHES, sender_name=sender_name, **kw)


def items(result):
    return {(i.product_code, i.quantity, i.unit) for i in result.items}


def test_document_example():
    r = parse("Please send 12 boxes of gloves to the Vijayawada branch tomorrow. Contact Ravi if needed.",
              sender_name="Ravi Kumar")
    assert items(r) == {("SS-GLV-M", 12, "box")}
    assert r.delivery_address == "Vijayawada branch, MG Road"
    assert r.requested_date == date(2026, 10, 13)
    assert any("Ravi" in n and "no phone" in n for n in r.notes)
    assert r.flags == []


def test_multiple_items_customer_phone_and_weekday():
    r = parse("Hi, this is Sri Sai Hospital. Need 20 strips paracetamol, 5 boxes N95 masks and "
              "2 BP monitors to Guntur by friday. call 98765 43210")
    assert items(r) == {("PH-PCM500", 20, "strip"), ("SS-N95", 5, "box"), ("ME-BPM", 2, "unit")}
    assert r.customer_name == "Sri Sai Hospital"
    assert r.contact_reference == "9876543210"
    assert r.requested_date == date(2026, 10, 16)


def test_quantity_after_product_and_unknown_location():
    r = parse("Need glucometer strips x 10 and 3 glucometer, deliver to Ramesh Medicals Tenali on 15/10")
    assert items(r) == {("ME-GSTR", 10, "box"), ("ME-GLU", 3, "unit")}
    assert r.requested_date == date(2026, 10, 15)
    assert [f["field"] for f in r.flags] == ["delivery_address"]


def test_unknown_product_is_flagged_not_guessed():
    r = parse("send 4 boxes of vitamin c tablets and 6 bottles cough syrup urgent")
    unknown = [i for i in r.items if i.product_id is None]
    assert len(unknown) == 1 and unknown[0].quantity == 4
    assert any("not in the product catalogue" in f["message"] for f in r.flags)
    assert r.requested_date == NOW.date()


def test_missing_details_are_all_flagged():
    r = parse("hello need some gloves")
    fields = {f["field"] for f in r.flags}
    assert fields == {"items", "delivery_address", "requested_date"}


def test_customer_flagged_when_sender_unknown():
    r = parse("5 boxes gloves to Guntur tomorrow", sender_name=None)
    assert {f["field"] for f in r.flags} == {"customer_name"}


def test_dozen_and_word_numbers():
    r = parse("two dozen gloves and three bp machines to Guntur on 20 oct")
    assert items(r) == {("SS-GLV-M", 24, "box"), ("ME-BPM", 3, "unit")}
    assert r.requested_date == date(2026, 10, 20)
