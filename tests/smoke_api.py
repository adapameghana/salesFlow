"""End-to-end smoke test against a RUNNING backend (python tests/smoke_api.py [base_url]).

Walks the MVP acceptance flow: login, import message, duplicate protection,
review/fix, confirm & route, department progress, permissions, reports.
Creates real records - run it on a test database or before loading demo data.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def call(method, path, body=None, token=None, expect=200):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status, data = resp.status, resp.read()
    except urllib.error.HTTPError as err:
        status, data = err.code, err.read()
    payload = json.loads(data) if data else None
    assert status == expect, f"{method} {path} -> {status} (expected {expect}): {payload}"
    return payload


def login(username):
    return call("POST", "/api/auth/login", {"username": username, "password": "Demo@123"})["access_token"]


def step(text):
    print(f"  ok  {text}")


def main():
    print(f"Smoke testing {BASE}")
    health = call("GET", "/api/health")
    assert health["database"] == "ok", health
    step(f"health: database ok, AI available={health['ai']['available']}")

    call("POST", "/api/auth/login", {"username": "operator", "password": "wrong"}, expect=401)
    op, pharmacy, surgical = login("operator"), login("pharmacy"), login("surgical")
    call("GET", "/api/orders", expect=401)
    step("login + unauthenticated access blocked")

    # 1. Complete message -> New order
    msg_id = f"SIM-{uuid.uuid4()}"
    text = "Please send 12 boxes of gloves to the Vijayawada branch tomorrow. Contact Ravi if needed."
    res = call("POST", "/api/messages/import", {
        "message_text": text, "sender_name": "Ravi Kumar", "sender_reference": "919900000001",
        "external_message_id": msg_id}, token=op)
    order = res["order"]
    assert not res["duplicate"] and order["status"] == "New", res
    step(f"message imported -> {order['order_number']} ({order['items_preview']})")

    # 2. Duplicate protection: same ID, then same text from the same sender
    dup = call("POST", "/api/messages/import", {
        "message_text": text, "sender_name": "Ravi Kumar", "sender_reference": "919900000001",
        "external_message_id": msg_id}, token=op)
    assert dup["duplicate"] and dup["order"]["id"] == order["id"]
    dup2 = call("POST", "/api/messages/import", {
        "message_text": text, "sender_name": "Ravi Kumar", "sender_reference": "919900000001",
        "external_message_id": f"SIM-{uuid.uuid4()}"}, token=op)
    assert dup2["duplicate"]
    step("duplicate message ID and repeated text both ignored")

    # 3. Confirm & route -> Surgical Supplies
    res = call("POST", f"/api/orders/{order['id']}/confirm", {}, token=op)
    order = res["order"]
    assert order["status"] == "Assigned" and order["department_name"] == "Surgical Supplies", order
    step(f"confirmed and routed: {res['routing']}")

    # 4. Department permissions
    call("GET", f"/api/orders/{order['id']}", token=pharmacy, expect=403)
    call("POST", f"/api/orders/{order['id']}/status", {"status": "In Progress"}, token=pharmacy, expect=403)
    pharmacy_list = call("GET", "/api/orders", token=pharmacy)
    assert all(o["department_name"] == "Pharmacy" for o in pharmacy_list["items"])
    step("other department cannot see or update the order")

    for status in ["In Progress", "Ready / Dispatched", "Completed"]:
        order = call("POST", f"/api/orders/{order['id']}/status", {"status": status, "comment": "smoke"}, token=surgical)
    call("POST", f"/api/orders/{order['id']}/notes", {"note": "Delivered with invoice"}, token=surgical, expect=201)
    assert order["status"] == "Completed"
    step("department moved order In Progress -> Ready / Dispatched -> Completed")

    # 5. Incomplete message -> Needs Review, cannot confirm until fixed
    res = call("POST", "/api/messages/import", {
        "message_text": "send 4 boxes of vitamin c tablets and 6 bottles cough syrup",
        "sender_name": "City Care Clinic", "sender_reference": "919900000002",
        "external_message_id": f"SIM-{uuid.uuid4()}"}, token=op)
    draft = res["order"]
    assert draft["status"] == "Needs Review" and draft["flag_count"] >= 2, draft
    call("POST", f"/api/orders/{draft['id']}/confirm", {}, token=op, expect=422)
    products = {p["product_code"]: p for p in call("GET", "/api/products", token=op)}
    fixed = call("PATCH", f"/api/orders/{draft['id']}", {
        "delivery_address": "Guntur branch, Brodipet, Guntur",
        "requested_date": "2030-01-01",
        "items": [{"product_id": products["PH-CSY100"]["id"], "quantity": 6},
                  {"product_id": products["PH-PCM500"]["id"], "quantity": 4}],
    }, token=op)
    assert fixed["status"] == "New" and fixed["flag_count"] == 0, fixed
    res = call("POST", f"/api/orders/{draft['id']}/confirm", {}, token=op)
    assert res["order"]["department_name"] == "Pharmacy"
    step("needs-review order blocked, corrected, then confirmed -> Pharmacy")

    # 6. Hold requires a reason; manual order; search; reports; audit
    call("POST", f"/api/orders/{draft['id']}/status", {"status": "On Hold"}, token=op, expect=422)
    call("POST", f"/api/orders/{draft['id']}/status", {"status": "On Hold", "comment": "Awaiting stock"}, token=op)
    manual = call("POST", "/api/orders", {
        "customer_name": "Walk-in", "delivery_address": "Nellore branch", "requested_date": "2030-01-02",
        "items": [{"product_id": products["ME-BPM"]["id"], "quantity": 2}]}, token=op, expect=201)
    assert manual["status"] == "New"
    found = call("GET", "/api/orders?q=Walk-in", token=op)
    assert found["total"] >= 1
    summary = call("GET", "/api/reports/summary", token=op)
    activity = call("GET", "/api/reports/activity", token=op)
    assert summary["total"] >= 3 and activity
    step(f"on-hold reason enforced, manual order, search, reports ({summary['total']} orders)")

    # 7. Preview with AI (falls back to rules if Ollama is down)
    preview = call("POST", "/api/messages/preview", {
        "message_text": "Need 10 strips of dolo and 2 oximeters for Apollo Clinic Tirupati by friday",
        "use_ai": True}, token=op)
    step(f"AI preview via {preview['method']}: {[(i['product_code'], i['quantity']) for i in preview['items']]}")

    stock_and_shop(op, surgical, products)
    print("All smoke checks passed.")


def stock_of(token, code):
    return next(r for r in call("GET", f"/api/inventory?q={code}", token=token) if r["product_code"] == code)


def stock_and_shop(op, surgical, products):
    equipment, admin = login("equipment"), login("admin")
    therm, bpm = products["ME-THERM"]["id"], products["ME-BPM"]["id"]

    # 8. Public catalogue shows levels only, never quantities
    catalogue = call("GET", "/api/public/catalogue")
    item = next(p for p in catalogue["products"] if p["product_code"] == "ME-THERM")
    assert set(item) == {"id", "product_code", "product_name", "unit", "description", "category", "stock_level",
                         "unit_price"}, item
    branch = catalogue["branches"][0]
    step(f"public catalogue: {len(catalogue['products'])} products, levels only (thermometer = {item['stock_level']})")

    # 9. Shop order larger than stock -> Needs Review with a stock flag, cannot confirm
    before = stock_of(op, "ME-THERM")
    want = before["available"] + 20
    phone = f"+91 9{uuid.uuid4().int % 10**9:09d}"
    shop = {"customer_name": "Smoke Test Clinic", "phone": phone, "branch_id": branch["id"],
            "requested_date": "2030-01-05", "items": [{"product_id": therm, "quantity": want}]}
    call("POST", "/api/public/orders", {**shop, "website": "spam"}, expect=422)
    call("POST", "/api/public/orders", {**shop, "requested_date": "2020-01-01"}, expect=422)
    placed = call("POST", "/api/public/orders", shop, expect=201)
    number = placed["order_number"]
    found = call("GET", f"/api/orders?q={number}", token=op)["items"][0]
    assert found["status"] == "Needs Review" and found["extraction_method"] == "shop", found
    detail = call("GET", f"/api/orders/{found['id']}", token=op)
    assert any(f["field"] == "stock" for f in detail["review_flags"]), detail["review_flags"]
    call("POST", f"/api/orders/{found['id']}/confirm", {}, token=op, expect=422)
    step(f"shop order {number} for {want:g} thermometers -> Needs Review: {detail['review_flags'][0]['message']}")

    # 10. Who may add stock
    call("POST", f"/api/inventory/{therm}/receive", {"quantity": 30}, token=op, expect=403)
    call("POST", f"/api/inventory/{therm}/receive", {"quantity": 30}, token=surgical, expect=403)
    call("GET", f"/api/inventory/{therm}/movements", token=surgical, expect=403)
    row = call("POST", f"/api/inventory/{therm}/receive", {"quantity": 30, "reason": "Supplier delivery"}, token=equipment)
    assert row["available"] == before["available"] + 30, row
    step("operator / other department blocked; equipment desk received 30 thermometers")

    # 11. Confirm reserves, adjusting below reserved is refused, dispatch deducts
    res = call("POST", f"/api/orders/{found['id']}/confirm", {}, token=op)
    assert res["order"]["department_name"] == "Medical Equipment" and res["order"]["stock_state"] == "reserved"
    row = stock_of(op, "ME-THERM")
    assert row["reserved"] == before["reserved"] + want and row["available"] == before["available"] + 30 - want, row
    call("POST", f"/api/inventory/{therm}/adjust", {"delta": -row["on_hand"], "reason": "count"}, token=equipment, expect=422)
    for status in ["In Progress", "Ready / Dispatched"]:
        call("POST", f"/api/orders/{found['id']}/status", {"status": status}, token=equipment)
    row = stock_of(op, "ME-THERM")
    assert row["on_hand"] == before["on_hand"] + 30 - want and row["reserved"] == before["reserved"], row
    kinds = [m["type"] for m in call("GET", f"/api/inventory/{therm}/movements", token=equipment)[:3]]
    assert kinds == ["dispatch", "reserve", "in"], kinds
    step(f"confirm reserved {want:g}, dispatch deducted it (on hand now {row['on_hand']:g})")

    # 12. Customer tracking needs the matching phone
    call("GET", f"/api/public/orders/{number}?phone=9000000000", expect=404)
    tracked = call("GET", f"/api/public/orders/{number}?phone={phone.replace(' ', '')}")
    assert tracked["status"] == "Dispatched", tracked
    step(f"tracking: wrong phone 404, right phone -> {' > '.join(t['status'] for t in tracked['timeline'])}")

    # 13. Editing a reserved order re-checks stock; cancelling releases the reservation
    before = stock_of(op, "ME-BPM")
    placed = call("POST", "/api/public/orders", {**shop, "items": [{"product_id": bpm, "quantity": 1}]}, expect=201)
    second = call("GET", f"/api/orders?q={placed['order_number']}", token=op)["items"][0]
    call("POST", f"/api/orders/{second['id']}/confirm", {}, token=op)
    assert stock_of(op, "ME-BPM")["reserved"] == before["reserved"] + 1
    call("PATCH", f"/api/orders/{second['id']}", {"items": [{"product_id": bpm, "quantity": 9999}]}, token=op, expect=422)
    assert stock_of(op, "ME-BPM")["reserved"] == before["reserved"] + 1
    call("POST", f"/api/orders/{second['id']}/status", {"status": "Cancelled", "comment": "Customer cancelled"}, token=op)
    assert stock_of(op, "ME-BPM")["reserved"] == before["reserved"]
    summary = call("GET", "/api/reports/summary", token=admin)
    assert "low_stock_count" in summary
    step(f"oversized edit refused, cancel released stock; {summary['low_stock_count']} products low/out")

    payments(op, admin, shop, bpm)


def payments(op, admin, shop, bpm):
    # 14. Prices fill the order amount; part payment, full payment, removal
    price = call("GET", "/api/public/catalogue")
    bpm_price = next(p["unit_price"] for p in price["products"] if p["id"] == bpm)
    placed = call("POST", "/api/public/orders", {**shop, "items": [{"product_id": bpm, "quantity": 2}]}, expect=201)
    order = call("GET", f"/api/orders?q={placed['order_number']}", token=op)["items"][0]
    assert order["amount_due"] == 2 * bpm_price and order["payment_status"] == "Unpaid", order
    oid = order["id"]
    call("POST", f"/api/orders/{oid}/payments", {"amount": order["amount_due"] + 1, "method": "cash"}, token=op, expect=422)
    half = call("POST", f"/api/orders/{oid}/payments", {"amount": bpm_price, "method": "upi", "reference": "UTR1"},
                token=op, expect=201)
    assert half["payment_status"] == "Partially Paid" and half["balance"] == bpm_price, half
    full = call("POST", f"/api/orders/{oid}/payments", {"amount": bpm_price, "method": "cash"}, token=op, expect=201)
    assert full["payment_status"] == "Paid" and full["balance"] == 0
    first = full["payments"][0]["id"]
    call("DELETE", f"/api/orders/{oid}/payments/{first}", {"reason": "smoke"}, token=op, expect=403)
    back = call("DELETE", f"/api/orders/{oid}/payments/{first}", {"reason": "smoke test"}, token=admin)
    assert back["payment_status"] == "Partially Paid"
    due = call("GET", "/api/orders?payment_status=Unpaid&payment_status=Partially%20Paid", token=op)
    assert any(o["id"] == oid for o in due["items"])
    step(f"order of {2 * bpm_price:g} -> part paid -> paid -> payment removed by admin -> Partially Paid")


if __name__ == "__main__":
    main()
