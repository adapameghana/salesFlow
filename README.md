# WhatsApp Order Automation – Local MVP

A locally hosted system that captures orders from WhatsApp messages and from a public online shop
page, turns them into structured orders, checks them against stock, routes them to departments and
tracks each order to completion. Everything runs on this
computer; there is no cloud hosting, cloud database or cloud AI.

| Layer | Technology (all open source) |
|---|---|
| Frontend | Angular 21 – `http://localhost:4300` |
| Backend API | Python FastAPI + SQLAlchemy – `http://127.0.0.1:8000` (Swagger docs at `/docs`) |
| Database | PostgreSQL 17 |
| Optional AI | Ollama + `qwen2.5:1.5b`, running locally |
| WhatsApp | Local simulator (a real connector plugs in later; see `whatsapp-connector/`) |
| Online shop | Public page at `http://localhost:4300/shop` (no login) |

---

## 1. One-time setup

### Database (run the scripts yourself)
Edit the password in `database/01_create_database.sql` if you like, then run:

```bat
psql -U postgres -h localhost -f database\01_create_database.sql
psql -U wa_app  -h localhost -d whatsapp_orders -f database\02_schema.sql
psql -U wa_app  -h localhost -d whatsapp_orders -f database\03_seed_data.sql
```

You can also run `scripts\setup-database.bat`, which runs all three scripts.

| Script | What it does |
|---|---|
| `01_create_database.sql` | Creates the role `wa_app` (password `wa_app_password`) and the database `whatsapp_orders` |
| `02_schema.sql` | Creates 11 tables, constraints and indexes |
| `03_seed_data.sql` | Loads 4 departments, 7 demo users, 14 products (with opening stock), 7 branches and 4 routing rules |
| `04_reset_demo_data.sql` | *Optional.* Deletes all orders, messages and stock movements, keeps master data and puts stock back to the opening levels. Use it before a demo |
| `05_inventory_and_shop.sql` | **Only for a database created before stock and the shop were added.** Adds the stock columns, the `stock_movements` table and the opening stock. Safe to run twice |
| `06_fix_table_ownership.sql` | *Repair, run as `postgres`.* Gives every table back to `wa_app`. Use it if the backend fails with "permission denied for table …" |

**Already created the database earlier?** Run just the upgrade, then restart the backend:
```bat
psql -U wa_app -h localhost -d whatsapp_orders -f database\05_inventory_and_shop.sql
```

If you changed the password, update `DATABASE_URL` in `backend\.env`.

### Backend
```bat
cd backend
pip install -r requirements.txt
```

### Frontend
```bat
cd frontend
npm install
```

### Local AI (optional)
```bat
ollama pull qwen2.5:1.5b
```
If Ollama isn't running, the app still works: it uses the rules-based parser and the AI toggle is disabled.

## 2. Run it

```bat
scripts\start-demo.bat
```
This opens two windows (backend and frontend). Then browse to:

| URL | Who |
|---|---|
| **http://localhost:4300** | Staff (log in) |
| **http://localhost:4300/shop** | Customers: browse products and order, no login |
| **http://localhost:4300/shop/track** | Customers: track an order with its number and phone |

Every demo user has the password **`Demo@123`**:

| User | Role | Sees |
|---|---|---|
| `operator` | Order operator | Simulator, inbox, review queue, all orders, inventory (view only) |
| `supervisor` / `admin` | Supervisor / admin | Everything, plus Settings (rules, catalogue, users) and stock for all products |
| `surgical`, `pharmacy`, `equipment`, `dispatch` | Department user | Only orders routed to their own department, and stock in / adjust for their own products |

### How stock works
- **Available = on hand − reserved.** The shop shows only *In stock / Low stock / Out of stock*, never quantities.
- An order for more than is available still comes in, but lands in **Needs Review** with a message such as
  "Only 3 unit of Digital Thermometer in stock (ordered 15)". It cannot be confirmed until stock arrives or the quantity is changed.
- **Confirm & route** reserves the stock. **Mark dispatched** (or completing it directly) takes it out of on-hand.
  **Cancel** gives the reservation back. Editing the items of a confirmed order re-checks stock.
- **Inventory** page: *+ Stock in* when goods arrive, *Adjust* (with a reason) for counts, damage or expiry, and *History* for every movement.
- "Low stock" means available ≤ the product's reorder level (set in Settings → Product catalogue). The dashboard lists low and out-of-stock products.

## 3. Suggested demo flow (about 10 minutes)

1. **Log in as `operator`.** Point out the sidebar: local database, local AI, and no cloud services.
2. **WhatsApp Simulator.** Send the sample messages one after another:
   - *Clean order*: becomes **New** with every field extracted.
   - *Unknown product* and *Missing details*: become **Needs Review**, with clear reasons. Nothing is guessed.
   - *Emergency rule*: on confirmation, this one is routed to Dispatch by a routing rule.
   - Turn on **Use local AI** and send *Equipment*. Ollama extracts the order locally.
   - Click **Simulate retry**. The duplicate is detected and no second order is created.
3. **Review Queue.** Open the *vitamin C* order and replace the unknown item with a catalogue product. Click **Save**, then **Confirm & route**. It's routed to Pharmacy automatically.
4. **Log out and log in as `surgical`.** That user sees only Surgical Supplies orders. Open one, then click **Start work**, **Mark dispatched** and **Mark completed**, and add a note.
5. **Log in as `supervisor`.** Show the Dashboard (KPIs, workload, activity log) and Orders (search, filters, delayed). In Settings, add a routing rule live, for example keyword `repair` → Medical Equipment.
6. **Customer shop and stock.** Open **http://localhost:4300/shop** in a second window, as the customer.
   - Point out that the Pulse Oximeter is *Out of stock* and Insulin is *Low stock*.
   - Order 2 BP monitors and 15 thermometers to the Tirupati branch, then place the order. Note the order number.
   - As `operator`, open it in **Review Queue**: *Needs Review – only 3 thermometers in stock*.
   - As `equipment`, go to **Inventory**, click **+ Stock in** for ME-THERM and add 20 units.
   - As `operator`, click **Confirm & route**. The stock is now reserved, and Inventory shows it.
   - As `equipment`, click **Start work**, then **Mark dispatched**. On hand goes down; **History** shows every step.
   - Back on the shop, go to **Track an order**, enter the order number and phone, and show the status *Dispatched*.
7. Open **http://127.0.0.1:8000/docs** to show the documented REST API.

To start again with an empty dashboard, run `database/04_reset_demo_data.sql` and refresh the browser.

## 4. Backup and restore (FR-10)
```bat
scripts\backup.bat                                   :: writes backups\whatsapp_orders_<timestamp>.dump
scripts\restore.bat backups\whatsapp_orders_<...>.dump
```
Copy the `backups` folder to a separate drive. Backups contain customer data, so protect them accordingly.

## 5. Tests
```bat
python -m pytest tests                 :: parser unit tests (no server needed)
python tests\smoke_api.py              :: end-to-end API flow against a running backend
```
`smoke_api.py` creates real orders. Run it before resetting the demo data, not afterwards.

## 6. How the pieces fit together

```
WhatsApp Simulator ─┐
(future connector) ─┴─► POST /api/messages/import ─► duplicate check (message ID, or same text within 30 min)
                               │
                               ▼
                 rules parser  ──or──  local AI (Ollama) + catalogue validation
                               │
Online shop (/shop) ───────────┤  POST /api/public/orders (no login, rate limited)
Manual entry ──────────────────┤  POST /api/orders
                               ▼
     order draft: New / Needs Review (missing details + stock shortages) ─► operator edits ─► Confirm & route
                                                                                                   │
                                     reserve stock ◄── routing rules (priority) → product department
                                                                                                   │
                     department queue: Assigned → In Progress → Ready / Dispatched → Completed
                                                                (stock deducted)
                     Cancelled releases reserved stock. On Hold / Cancelled require a reason;
                     every step goes to history, the audit log and (for stock) stock_movements.
```

### Project layout
```
backend/app/
  main.py, config.py, database.py, security.py
  api/        auth, orders, messages, departments, admin (users/products/branches/rules), reports,
              inventory (stock levels, stock in, adjust, history), shop (public catalogue, orders, tracking)
  models/     SQLAlchemy entities (the tables come from database/02_schema.sql)
  schemas/    request/response models
  services/   message_parser (rules), ai_parser (Ollama), intake_service, order_service, routing_service,
              stock_service (levels, shortages, reserve / release / dispatch)
  connectors/ connector interface for a future WhatsApp provider
frontend/src/app/
  pages/      login, dashboard, simulator, inbox, orders-list, order-detail, order-form, admin, inventory,
              shop + shop-track (public, no login)
database/     SQL scripts 01-05
scripts/      start / setup / backup / restore helpers
tests/        parser and stock unit tests, and the API smoke test
```

### Configuration (`backend/.env`)
| Setting | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://wa_app:wa_app_password@localhost:5432/whatsapp_orders` | Database connection |
| `JWT_SECRET` | *(change me)* | Signs login tokens |
| `AI_ENABLED` | `true` | Set to `false` to hide the AI option completely |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://127.0.0.1:11434` / `qwen2.5:1.5b` | Local AI |
| `BUSINESS_UTC_OFFSET_MINUTES` | `330` (IST) | Used to resolve "today", "tomorrow" and "friday" |

### Security notes
- Both servers bind to `127.0.0.1` only. For office LAN access, change the host deliberately and add firewall rules or HTTPS (Nginx).
- Passwords are stored as bcrypt hashes. Change `JWT_SECRET` and the demo passwords before real use.
- No message content leaves the machine. AI calls go only to the local Ollama.
- The shop is "public" only in the sense that it needs no login. Like the rest of the app it is served on
  this computer. Putting it on the internet needs a reverse proxy with HTTPS (for example Nginx) and is out of scope for the MVP.
  The shop never shows stock quantities, has a hidden spam trap field and accepts at most 10 orders per device every 10 minutes.
  Tracking needs both the order number and the matching phone number.
