"""Unit tests for stock levels and shortage flags (no database). Run:  python -m pytest tests"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.models import Order, OrderItem, Product  # noqa: E402
from app.services.stock_service import demand_of, fmt, level_for, shortage_flags  # noqa: E402


def product(pid, name, on_hand, reserved=0, reorder=10, unit="box"):
    return Product(id=pid, product_code=f"P{pid}", product_name=name, unit=unit,
                   stock_on_hand=Decimal(on_hand), stock_reserved=Decimal(reserved), reorder_level=Decimal(reorder))


def order(*lines):
    o = Order()
    for pid, qty in lines:
        o.items.append(OrderItem(product_id=pid, product_name="x", quantity=None if qty is None else Decimal(qty)))
    return o


def test_levels():
    assert level_for(Decimal(0), Decimal(5)) == "out"
    assert level_for(Decimal(-1), Decimal(5)) == "out"
    assert level_for(Decimal(5), Decimal(5)) == "low"
    assert level_for(Decimal(6), Decimal(5)) == "ok"


def test_available_subtracts_reserved():
    assert product(1, "Gloves", 50, reserved=20).available == Decimal(30)


def test_demand_sums_lines_and_skips_unknown_or_empty():
    o = order((1, 10), (1, 5), (2, None), (None, 3))
    assert demand_of(o) == {1: Decimal(15)}


def test_no_flags_when_enough_stock():
    assert shortage_flags({1: Decimal(30)}, {1: product(1, "Gloves", 50, reserved=20)}) == []


def test_short_and_out_of_stock_flags():
    products = {1: product(1, "Gloves", 50, reserved=45), 2: product(2, "Oximeter", 0, unit="unit")}
    flags = shortage_flags({1: Decimal(10), 2: Decimal(2)}, products)
    messages = [f["message"] for f in flags]
    assert messages == [
        "Only 5 box of Gloves in stock (ordered 10).",
        "Oximeter is out of stock (ordered 2 unit).",
    ]
    assert all(f["field"] == "stock" for f in flags)


def test_fmt():
    assert fmt(Decimal("20.00")) == "20"
    assert fmt(Decimal("2.50")) == "2.5"
