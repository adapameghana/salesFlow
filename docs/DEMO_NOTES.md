# WhatsApp Order Automation – Demo Notes

_Prepared: 14 Oct 2026_

---

## 1. Overview

The app turns WhatsApp messages and online-shop orders into structured orders. It checks stock, sends each order to the right department and tracks it until it is completed. It runs entirely on one computer, with no cloud hosting, cloud database or cloud AI.

- **Problem it solves:** orders that arrive as free-text WhatsApp messages are typed in by hand. They get missed, duplicated or sent to the wrong team, and stock problems show up too late.
- **Who uses it:**
  - Order operators: intake and review
  - Department users: Surgical, Pharmacy, Equipment, Dispatch
  - Supervisors and admins: oversight and settings
  - Customers: public shop and order tracking
- **One-line pitch:** "Message in, order out. Parsed, stock-checked, routed and tracked, and nothing leaves the building."

---

## 2. Key features to highlight

| Feature | What to say | Where to show it |
|---|---|---|
| Message parsing | Free-text WhatsApp messages become orders. Customer, branch, items, quantities and dates are extracted | WhatsApp Simulator |
| Nothing is guessed | Unknown products or missing details go to **Needs Review** with a clear reason | Review Queue |
| Local AI (optional) | Ollama with qwen2.5:1.5b extracts orders on this machine. If it is offline, the rules parser is used instead | Simulator → *Use local AI* |
| Duplicate protection | The same message ID, or the same text within 30 min, never creates a second order | Simulator → *Simulate retry* |
| Automatic routing | Routing rules (by priority) decide who gets the order. If no rule matches, the product's department gets it | Confirm & route; Settings → rules |
| Department queues | Each department sees only its own orders: Assigned → In Progress → Dispatched → Completed | Log in as `surgical` |
| Stock control | Available = on hand − reserved. Confirming reserves stock, dispatching deducts it and cancelling releases it | Inventory page + History |
| Public online shop | Customers order without logging in. They see only In / Low / Out of stock, never quantities | `/shop` |
| Order tracking | Customers track an order with the order number and their phone number | `/shop/track` |
| Supervisor dashboard | KPIs, workload by department, delayed orders, low-stock list, activity log | Dashboard |
| Audit trail | Every status change, edit and stock movement is logged | Order detail, Inventory history |
| Data privacy | Servers listen on 127.0.0.1 only, passwords are bcrypt-hashed and no message leaves the machine | Talking point |
| REST API | Fully documented and ready for a real WhatsApp connector | `http://127.0.0.1:8000/docs` |

---

## 3. Architecture and tech stack

| Layer | Technology |
|---|---|
| Frontend | Angular 21 at `http://localhost:4300` |
| Backend API | Python FastAPI + SQLAlchemy at `http://127.0.0.1:8000` |
| Database | PostgreSQL 17 |
| AI (optional) | Ollama + `qwen2.5:1.5b`, local |
| WhatsApp | Local simulator now; a real provider plugs into `whatsapp-connector/` later |

**Flow in one picture:**

```
WhatsApp message ─┐
Online shop ──────┼─► Duplicate check ─► Parser (rules or local AI) ─► Order: New / Needs Review
Manual entry ─────┘                                                          │
                                                             Operator edits ─► Confirm & route
                                                                                     │
                                      Routing rules → Department queue (stock reserved)
                                                                                     │
                                Assigned → In Progress → Dispatched (stock deducted) → Completed
```

---

## 4. Before the demo: setup checklist

Do these 15 minutes before you start, so the dashboard starts empty and every service is running.

- [ ] PostgreSQL 17 is running
- [ ] Reset the demo data: `psql -U wa_app -h localhost -d whatsapp_orders -f database\04_reset_demo_data.sql`
- [ ] Ollama is running with `qwen2.5:1.5b` (only needed if you are showing the AI part)
- [ ] Run `scripts\start-demo.bat`. Check that the backend and frontend windows both open without errors
- [ ] The staff app loads at `http://localhost:4300`
- [ ] A second browser window (or incognito window) is open at `http://localhost:4300/shop` for the customer view
- [ ] The Swagger API page loads at `http://127.0.0.1:8000/docs`
- [ ] Every user's password is `Demo@123`. Users: `operator`, `supervisor`, `admin`, `surgical`, `pharmacy`, `equipment`, `dispatch`
- [ ] Do **not** run `tests\smoke_api.py` after the reset, because it creates real orders
- [ ] Close unrelated tabs and zoom the browser to about 110%

---

## 5. Demo script (about 10–15 minutes)

1. **Intro (1 min).** Log in as `operator`.
   - Say: everything you'll see runs locally, with a local database, local AI and no cloud.
   - Point out the sidebar: Simulator, Inbox, Review Queue, Orders, Inventory.
2. **WhatsApp Simulator (3 min).** Send the sample messages one at a time.
   - *Clean order*: it becomes **New**, with every field extracted.
   - *Unknown product* and *Missing details*: they become **Needs Review** with clear reasons. Say: "Nothing is guessed."
   - *Emergency rule*: mention it. When it is confirmed, a routing rule sends it to Dispatch.
   - Turn on **Use local AI** and send *Equipment*. Ollama extracts the order on this machine.
   - Click **Simulate retry**. The duplicate is detected and no second order is created.
3. **Review Queue (2 min).** Open the *vitamin C* order.
   - Replace the unknown item with a catalogue product, click **Save**, then click **Confirm & route**.
   - Say: it went to Pharmacy automatically.
4. **Department view (2 min).** Log out and log in as `surgical`.
   - Only Surgical Supplies orders are visible.
   - Open one, click **Start work** → **Mark dispatched** → **Mark completed**, and add a note.
5. **Supervisor view (2 min).** Log in as `supervisor`.
   - Dashboard: KPIs, department workload, low-stock list, activity log.
   - Orders: search, filters, delayed orders.
   - Settings: add a routing rule live, for example keyword `repair` → Medical Equipment.
6. **Customer shop and stock (4 min).** Switch to the second window at `/shop`.
   - Show that Pulse Oximeter is *Out of stock* and Insulin is *Low stock*. No quantities are shown.
   - Order 2 BP monitors and 15 thermometers to the Tirupati branch. Note the order number.
   - As `operator`: the Review Queue shows *Needs Review – only 3 thermometers in stock*.
   - As `equipment`: go to Inventory, click **+ Stock in** for ME-THERM and add 20 units.
   - As `operator`: click **Confirm & route**. The stock is now reserved.
   - As `equipment`: click **Start work**, then **Mark dispatched**. On-hand stock drops, and **History** shows each step.
   - Back in the shop: go to **Track an order**, enter the order number and phone number, and show the status *Dispatched*.
7. **API (1 min).** Open `http://127.0.0.1:8000/docs`.
   - Say: this is a documented REST API, and a real WhatsApp provider plugs into the connector interface next.
8. **Wrap-up.** Recap the three wins: no manual typing, the right department every time, and live stock visibility.

---

## 6. Likely questions and answers

| Question | Answer |
|---|---|
| Does it connect to real WhatsApp? | Not yet. The demo uses a simulator. A connector interface is ready, so a provider (for example the WhatsApp Business API) can be added next |
| Is customer data sent to the cloud? | No. The database, AI and servers all run on this machine |
| What if the AI is wrong or offline? | The rules parser always works. Anything uncertain goes to Needs Review, and a person confirms it |
| What stops duplicate orders? | Same message ID, or same text within 30 minutes, is detected and skipped |
| What happens if stock is short? | The order still comes in, but it goes to Needs Review and can't be confirmed until stock arrives or the quantity changes |
| Can customers see our stock levels? | No. They only see In stock, Low stock or Out of stock |
| Who can see which orders? | Department users see only their own department. Supervisors and admins see everything |
| Is there a backup? | Yes. `scripts\backup.bat` and `scripts\restore.bat` |
| Can it be used across the office network? | Yes, after deliberately changing the host and adding firewall rules or HTTPS (Nginx) |

**Known limitations (be upfront if asked):**
- WhatsApp is simulated, so there is no live number yet.
- The app runs on a single machine and has not been hardened for internet exposure.
- Demo passwords and `JWT_SECRET` must be changed before real use.

**Possible next steps:**
- Connect a real WhatsApp Business API provider
- Deploy on the office LAN with HTTPS
- Send notifications to customers when the order status changes

---

## 7. My notes

_Use this space for your own points, timings and reminders._

-
-
-
