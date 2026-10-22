from datetime import date

import pytest

from voice_agent.models import CallContext

TODAY = date(2026, 10, 22)  # a Thursday


def make_ctx(lang: str = "en", **overrides) -> CallContext:
    data = {
        "order_id": 7, "order_number": "ORD-2026-0007", "customer_name": "Sri Sai Clinic",
        "language": lang, "balance": 4250.0, "amount_due": 5000.0, "amount_paid": 750.0,
        "business_name": "Dhanush Healthcare", "attempt_no": 1,
        "items": [{"name": "Nitrile gloves M", "quantity": 5, "unit": "box"}],
        "today": TODAY.isoformat(),
    }
    data.update(overrides)
    return CallContext.from_dict(data)


@pytest.fixture
def ctx_factory():
    return make_ctx
