"""Department routing: configurable rules first, then the product's own department."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Order, RoutingRule


@dataclass
class RouteDecision:
    department_id: int | None
    reason: str


def route_order(db: Session, order: Order, message_text: str = "") -> RouteDecision:
    rules = db.scalars(
        select(RoutingRule).where(RoutingRule.active.is_(True)).order_by(RoutingRule.priority, RoutingRule.id)
    ).all()
    codes = {i.product.product_code.upper() for i in order.items if i.product}
    searchable = " ".join(filter(None, [message_text, order.notes] + [i.product_name for i in order.items])).lower()
    address = (order.delivery_address or "").lower()

    for rule in rules:
        value = rule.match_value.strip().lower()
        if (
            (rule.match_field == "product" and value.upper() in codes)
            or (rule.match_field == "keyword" and value in searchable)
            or (rule.match_field == "location" and value in address)
        ):
            return RouteDecision(rule.target_department_id, f"Routing rule: {rule.rule_name}")

    for item in order.items:
        if item.product and item.product.department_id:
            return RouteDecision(item.product.department_id, f"Product department of {item.product.product_name}")

    return RouteDecision(None, "No routing rule matched - assign manually")
