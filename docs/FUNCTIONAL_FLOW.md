# WhatsApp Order Automation – Functional Flow

**Version:** 1.1 (Local MVP + stock and online shop)  
**Date:** 13 October 2026  
**Deployment:** Local computer / office network only. No cloud services.

---

## Contents

1. [Purpose](#1-purpose)
2. [Users and roles](#2-users-and-roles)
3. [End-to-end flow](#3-end-to-end-flow)
4. [Stage-by-stage description](#4-stage-by-stage-description)
5. [Order status lifecycle](#5-order-status-lifecycle)
6. [Permissions matrix](#6-permissions-matrix)
7. [Worked example](#7-worked-example)
8. [Exception handling](#8-exception-handling)
9. [Master data and configuration](#9-master-data-and-configuration)
10. [Requirement traceability](#10-requirement-traceability)
11. [Out of scope for this MVP](#11-out-of-scope-for-this-mvp)
12. [Stock management](#12-stock-management)
13. [Online shop for customers](#13-online-shop-for-customers)
14. [Prices and payments](#14-prices-and-payments)

---

## 1. Purpose

This document describes how an order moves through the system: from a customer's WhatsApp
message or online shop order, through review, stock check, confirmation, department routing and
processing, to completion.

The system:

- **Captures** orders from WhatsApp messages, the public online shop, or manual entry
- **Extracts** structured details (items, quantities, location, date) from free text
- **Validates** every order, including stock availability, and asks a person to check anything unclear
- **Reserves and deducts stock** as orders are confirmed and dispatched
- **Routes** confirmed orders to the right department automatically
- **Tracks** each order to completion, with a full history and audit trail

---

## 2. Users and roles

| Role | Demo login | Responsibilities |
|---|---|---|
| **Customer** | WhatsApp simulator, or the shop at `/shop` (no login) | Sends order messages on WhatsApp, or orders on the online shop and tracks the order |
| **Order operator** | `operator` | Reviews incoming orders, corrects details, confirms and assigns orders |
| **Department user** | `pharmacy`, `surgical`, `equipment`, `dispatch` | Processes orders routed to their own department, updates progress, and adds stock for their own products |
| **Supervisor** | `supervisor` | Monitors reports and manages routing rules, products, branches and users |
| **Administrator** | `admin` | Full access, including user management |

Every demo account uses the password `Demo@123`.

---

## 3. End-to-end flow

```
 CUSTOMER              OPERATOR                   SYSTEM                     DEPARTMENT
 ────────              ────────                   ──────                     ──────────
 Sends WhatsApp ─────────────────────────► ① Receive & store message
 message                                   ② Duplicate check
                                           ③ Extract order details
 Orders on the                                   │
 online shop ─────────────────────────────────── ┤ (items already structured)
                                                 ▼
                                           ④ Create draft order + stock check
                                              (New / Needs Review)
                       ⑤ Review & correct ◄──────────┘
                       ⑥ Confirm ────────► reserve stock
                                           ⑦ Route to department ───────► ⑧ Process order
                                                                           In Progress →
                                                                           Ready / Dispatched (stock out) →
                                                                           Completed
 Tracks order ◄──── order number + phone      SUPERVISOR ◄── ⑨ Dashboard, low-stock alerts, reports, audit
```

---

## 4. Stage-by-stage description

### ① Receive message

| | |
|---|---|
| **Trigger** | A customer sends a WhatsApp message (simulated in the MVP) |
| **Actor** | System |
| **What happens** | The message text, sender name, phone number, received time and message ID are stored |
| **Where to see it** | **Message Inbox** page |
| **Other ways in** | **Online shop** (`/shop`), where customers pick products from the catalogue (see section 13) · **Manual order entry**, for phone orders, walk-ins, or when WhatsApp is unavailable |

The WhatsApp simulator and a future real WhatsApp connector both use the same intake
point, so the rest of the flow doesn't change when the real connector is added.

### ② Duplicate check

WhatsApp providers can deliver the same message more than once. The system checks two cases:

| Check | Rule | Result |
|---|---|---|
| Same message ID | The ID has already been received from this source | Ignored. No new order is created |
| Same content | Identical text from the same phone number within 30 minutes | Stored with state **Duplicate** and linked to the original order. No new order is created |

### ③ Extract order details

The free-text message is converted into structured fields.

| Field | How it is identified | Example |
|---|---|---|
| **Items** | Matched against the product catalogue, including alternative names | "dolo" → Paracetamol 500mg Tablets |
| **Quantity and unit** | The number next to the product, with units like boxes, strips, bottles or dozen | "12 boxes of gloves" → 12 box · "two dozen" → 24 |
| **Customer** | Phrases such as "this is … Hospital" or "for … Clinic", otherwise the sender's name | "Sri Sai Hospital" |
| **Contact** | A phone number in the message, otherwise the sender's number | 9876543210 |
| **Delivery location** | Matched against the branch list, otherwise the text after "to" / "deliver to" | "Vijayawada branch" |
| **Requested date** | Words and dates resolved in business time (IST) | "tomorrow", "friday", "20/10", "18th oct", "urgent" (= today) |
| **Notes** | Contact person, urgency | "Contact person: Ravi" |

**Extraction methods**

| Method | When it's used | Behaviour |
|---|---|---|
| **Rules-based** (default) | Always available | Fast and predictable. Works with no AI installed |
| **Local AI** (optional) | When **Use local AI** is ticked and Ollama is running | The local model reads the message. Its output is checked against the catalogue and branches, and gaps are filled from the rules. If AI is unavailable, the system falls back to rules automatically |

No message content is sent outside the computer.

### ④ Create draft order

- An order number is generated in the format `ORD-YYYYMMDD-NNNN`.
- The draft is checked, and its starting status is set:

| Condition | Initial status |
|---|---|
| Every required detail found and valid | **New** |
| Any detail missing or uncertain | **Needs Review**, with the reasons listed |

**Reasons an order goes to Needs Review**

- A product is not in the catalogue
- A quantity is missing
- The delivery location is missing, or is not a known branch
- The requested date is missing, or is in the past
- The customer name is missing
- **There isn't enough stock** for an item, for example "Only 3 unit of Digital Thermometer in stock (ordered 15)" (see section 12)

> **Design principle:** the system never silently guesses important details. When it
> isn't sure, it flags the order for a person to check.

### ⑤ Operator review

| | |
|---|---|
| **Actor** | Order operator |
| **Where** | **Review Queue** (lists every order that is New or Needs Review) |
| **What they see** | The original WhatsApp message next to the extracted fields, with problems highlighted |
| **What they do** | Correct the customer, contact, location, date or items (choosing from the catalogue), then click **Save** |
| **System response** | Re-checks the order. If every problem is fixed, the status becomes **New**; otherwise it stays **Needs Review** |

### ⑥ Confirm

| | |
|---|---|
| **Actor** | Order operator |
| **Action** | **Confirm & route** |
| **Checks before confirming** | Customer, delivery location, requested date and at least one item; every item must be a catalogue product with a quantity above 0; **enough stock must be available for every item** |
| **If a check fails** | Confirmation is blocked and the problems are listed. A New order moves to Needs Review |
| **If every check passes** | The stock is **reserved**, the status becomes **Confirmed**, and routing runs immediately |

### ⑦ Route to department

Routing runs automatically when an order is confirmed:

```
Step 1 – Routing rules, in priority order (lowest number first). The first match wins.
          Rule types: keyword (in the message or notes) · product code · delivery location

Step 2 – If no rule matches, use the department of the order's first catalogue product.

Step 3 – If there is still no department, the operator assigns one manually.
```

**Default routing rules**

| Priority | Rule | Match | Department |
|---|---|---|---|
| 10 | Emergency orders go to Dispatch | keyword `emergency` | Dispatch & Logistics |
| 20 | Insulin is cold-chain | product `PH-INS10` | Pharmacy |
| 30 | Device repairs to Equipment | keyword `repair` | Medical Equipment |
| 50 | Masks to Surgical Supplies | product `SS-N95` | Surgical Supplies |

- After routing, the status becomes **Assigned**, and the reason is saved in the history.
- An operator can **re-assign** the order to another department, or to a specific user, at any time.

### ⑧ Department processing

| | |
|---|---|
| **Actor** | Department user |
| **Where** | **My Department Queue**. Only orders routed to their own department are visible |
| **Actions** | Start work → Mark dispatched → Mark completed · Put on hold (reason required) · Add internal notes |
| **Stock effect** | **Mark dispatched** (or Mark completed straight from In Progress) takes the reserved quantity out of stock on hand |

### ⑨ Tracking and reporting

| Feature | Details |
|---|---|
| **Dashboard** | Orders today (and how many came from the shop), awaiting review, in progress, delayed, completed; **stock alerts** for low and out-of-stock products; status breakdown; 7-day trend; workload by department; recent activity |
| **Orders search** | By order number, customer, product, phone or location; filter by status, department, date range, delayed only |
| **Order history** | Every status change with user, time and comment |
| **Audit log** | Logins, edits, confirmations, assignments, notes, duplicate detections, stock received and stock adjustments |
| **Customer tracking** | Customers check their order status on `/shop/track` with the order number and phone number |
| **Delayed orders** | Requested date has passed and the order is not yet dispatched, completed or cancelled |

---

## 5. Order status lifecycle

```
                ┌──────────────┐
  message ─────►│ New          │──────────┐
  or manual     └──────┬───────┘          │
                       │ issues found     │ Confirm (only if valid)
                ┌──────▼───────┐          │
                │ Needs Review │──────────┤
                └──────────────┘          ▼
                                  ┌──────────────┐   auto-routing
                                  │ Confirmed    │──────────────┐
                                  └──────────────┘              ▼
                                                        ┌──────────────┐
                                                        │ Assigned     │
                                                        └──────┬───────┘
                                                               ▼
                                     ┌──────────┐       ┌──────────────┐
                                     │ On Hold  │◄─────►│ In Progress  │
                                     └──────────┘       └──────┬───────┘
                                                               ▼
                                                        ┌────────────────────┐
                                                        │ Ready / Dispatched │
                                                        └──────┬─────────────┘
                                                               ▼
                                                        ┌──────────────┐
                                                        │ Completed    │
                                                        └──────────────┘

   Cancelled ← possible from any open status (a reason is required)

   Stock:  Confirm = reserve · Ready / Dispatched (or Completed) = deduct · Cancelled = release
```

| Status | Meaning | Next possible statuses |
|---|---|---|
| **New** | Captured, every required detail present, waiting for confirmation | Confirmed, Needs Review, Cancelled |
| **Needs Review** | Details missing or uncertain | Confirmed (after correction), Cancelled |
| **Confirmed** | Checked by an operator | Assigned, On Hold, Cancelled |
| **Assigned** | A department owns the order | In Progress, On Hold, Cancelled |
| **In Progress** | The department is working on it | Ready / Dispatched, Completed, On Hold, Cancelled |
| **On Hold** | Temporarily blocked (reason required) | Assigned, In Progress, Cancelled |
| **Ready / Dispatched** | Ready or sent out | Completed, On Hold |
| **Completed** | Finished | — (final) |
| **Cancelled** | Cancelled (reason required) | — (final) |

---

## 6. Permissions matrix

| Action | Operator | Department user | Supervisor / Admin |
|---|:---:|:---:|:---:|
| View all orders | ✅ | ❌ (own department only) | ✅ |
| Send / import messages, view inbox | ✅ | ❌ | ✅ |
| Create manual orders | ✅ | ❌ | ✅ |
| Edit order details | ✅ | ❌ | ✅ |
| Confirm & route | ✅ | ❌ | ✅ |
| Assign / re-assign | ✅ | ❌ | ✅ |
| Start work / dispatch / complete | ❌ | ✅ (own department) | ✅ |
| Put on hold | ✅ | ✅ (own department) | ✅ |
| Cancel | ✅ | ❌ | ✅ |
| Add internal notes | ✅ | ✅ (own department) | ✅ |
| Manage rules, products, branches, departments, users | ❌ | ❌ | ✅ |
| View inventory | ✅ | ✅ (own department) | ✅ |
| Stock in / adjust stock | ❌ | ✅ (own department's products) | ✅ |

---

## 7. Worked example

**Incoming message** from Suresh Babu (+91 97011 22334):

> "send 4 boxes of vitamin c tablets and 6 bottles cough syrup to Hyderabad urgent"

| Step | Result |
|---|---|
| ① Receive | The message is stored in the inbox |
| ② Duplicate check | Not a duplicate, so processing continues |
| ③ Extract | Cough Syrup 100ml ✅ 6 bottle · Vitamin C Tablets ❌ not in catalogue, 4 box · Hyderabad branch ✅ · "urgent" → today ✅ · Customer: Suresh Babu · Contact: 919701122334 |
| ④ Draft | `ORD-20261012-0003` created as **Needs Review**, with the reason "Vitamin C Tablets is not in the product catalogue" |
| ⑤ Review | The operator replaces Vitamin C with *Paracetamol 500mg Tablets* and clicks Save, so the status becomes **New** |
| ⑥ Confirm | The operator clicks Confirm & route, so the status becomes **Confirmed** |
| ⑦ Route | No rule matches, so the order goes to the first product's department, **Pharmacy**. Status: **Assigned** |
| ⑧ Process | The pharmacy user moves it to In Progress → Ready / Dispatched → Completed and adds a delivery note |
| ⑨ Report | The order appears in the dashboard counts, and its history shows every step with user and time |

**More sample messages and their outcomes**

| Message | Outcome |
|---|---|
| "Please send 12 boxes of surgical gloves and 5 boxes of N95 masks to the Vijayawada branch tomorrow" | **New** → on confirmation, routed to Surgical Supplies (rule: Masks) |
| "EMERGENCY - 10 vials insulin to Nellore branch today" | **New** → on confirmation, routed to Dispatch & Logistics (rule: emergency) |
| "hello, we need some gloves" | **Needs Review**: quantity, location and date are missing |
| "deliver to Ramesh Medicals Tenali on 20/10" | **Needs Review**: the location is not a known branch |
| Shop order: 15 Digital Thermometers (3 in stock) | **Needs Review**: "Only 3 unit of Digital Thermometer in stock (ordered 15)". After the Equipment desk adds 20 units, it can be confirmed |

---

## 8. Exception handling

| Situation | System behaviour |
|---|---|
| Same message delivered again | Detected as a duplicate. No new order |
| Message can't be processed | Stored with state **Failed** and the error text. It can be retried from the Message Inbox |
| Local AI unavailable or slow | Falls back to rules-based extraction and adds a note to the order |
| Unknown product or location | The order is flagged for review. Nothing is guessed |
| Operator tries to confirm an incomplete order | Blocked, and the missing details are listed |
| On Hold / Cancel without a reason | Blocked until a reason is entered |
| Department user opens another department's order | Access denied |
| Not enough stock | The order is accepted but flagged **Needs Review**; confirmation is blocked until stock arrives or the quantity changes |
| Items of a confirmed order are increased beyond stock | The edit is refused and the existing reservation is kept |
| Stock adjusted below what confirmed orders have reserved | Refused |
| Shop: too many orders from one device, or the hidden spam field is filled | Refused |
| Shop tracking with a wrong phone number | "No order found" (the same answer as an unknown order number) |
| Login session expires | The user is returned to the login page |

---

## 9. Master data and configuration

Supervisors and admins maintain these under **Settings**:

| Data | Used for |
|---|---|
| **Product catalogue** (code, name, alternative names, unit, department, shop description, low-stock level) | Recognising items in messages, validating orders, fallback routing, the online shop, stock alerts |
| **Branches** (name, address) | Recognising and validating delivery locations |
| **Departments** | Order ownership and department queues |
| **Routing rules** (keyword / product / location → department, priority) | Automatic routing on confirmation |
| **Users** (role, department, active) | Login and permissions |

> Adding alternative names to a product, such as "dolo, crocin" for Paracetamol, improves
> automatic recognition straight away. No code change is needed.

---

## 10. Requirement traceability

| ID | Requirement | Implemented by |
|---|---|---|
| FR-01 | Capture orders | WhatsApp simulator, online shop and manual order entry |
| FR-02 | Preserve source message | Message Inbox; "Original WhatsApp message" on each order |
| FR-03 | Extract fields | Rules-based parser and optional local AI |
| FR-04 | Validate order | Needs Review flags; confirmation blocked until valid |
| FR-05 | Prevent duplicates | Message ID check and same-content check |
| FR-06 | Route order | Routing rules, product department fallback, manual re-assignment |
| FR-07 | Track progress | Status actions and internal notes |
| FR-08 | Search and filter | Orders page filters and search |
| FR-09 | Audit changes | Status history and audit log |
| FR-10 | Back up data | `scripts\backup.bat` and `scripts\restore.bat` |
| FR-11 | Manage users | Settings → Users; role-based access |
| FR-12 | Operate without cloud AI | Rules-based extraction by default; AI is local and optional |
| New | Stock management | Inventory page, reserve on confirm, deduct on dispatch, release on cancel, movement history |
| New | Customer self-ordering | Public `/shop` catalogue and checkout, `/shop/track` order tracking |
| New | Prices and payment tracking | Product prices, order amount from items, payments received, Unpaid / Partially Paid / Paid |

---

## 11. Out of scope for this MVP

- **Live WhatsApp connection.** The MVP uses a local simulator. A real connector needs an approved
  WhatsApp Business integration and internet access, and plugs into the same intake point.
- **Automatic replies to customers.** These need approved templates and customer consent first.
- **Taking payments online, invoicing and ERP integration.** Payments are recorded by staff after the customer
  has paid (see section 14); no payment gateway is connected and no card or bank details are stored.
- **Splitting one order across departments.** A mixed order goes to one owning department.
- **Internet-facing shop.** The shop runs on this computer; publishing it needs HTTPS and a reverse proxy.
- **Cloud hosting, cloud database or cloud AI.**

---

## 12. Stock management

Every product has **on hand**, **reserved** and a **low-stock level** (reorder level).

```
available = on hand − reserved

   Stock in / Adjust ──► on hand ±
   Confirm order ──────► reserved +           (available goes down)
   Cancel order ───────► reserved −           (available comes back)
   Dispatch order ─────► reserved − and on hand −
```

| Level | Rule | Shown as |
|---|---|---|
| OK | available > low-stock level | In stock |
| Low | 0 < available ≤ low-stock level | Low stock |
| Out | available ≤ 0 | Out of stock |

| Screen | Who | What |
|---|---|---|
| **Inventory** | Everyone (department users see their own products) | On hand, reserved, available, level; filters for low / out |
| **+ Stock in** | Managers, and the product's own department | Record goods received, with a supplier or invoice reference |
| **Adjust** | Same | Add or remove stock with a reason (count correction, damaged, expired, returned…). Cannot go below what is reserved |
| **History** | Everyone who can see the product | Every movement, with quantity, balance after, user and linked order |
| **Order page** | Office users | "Available now" next to each item, and a red *short* marker if there isn't enough |
| **Dashboard** | Everyone | Stock alerts for low and out-of-stock products |

Stock quantities are never typed into the product form. They change only through movements, so
every change is recorded in `stock_movements` and the audit log.

---

## 13. Online shop for customers

| | |
|---|---|
| **URL** | `http://localhost:4300/shop` (no login) |
| **What customers see** | Every active product with its category (department), description, unit, price and stock level (never stock quantities). The cart shows an estimated total |
| **Ordering** | Add products to a cart, then give name, phone, delivery branch (or another address), date needed and notes. The order number is shown straight away |
| **What happens next** | The order goes into the **Review Queue** exactly like a WhatsApp order (marked *Online shop order*). Nothing is reserved until an operator confirms it |
| **Tracking** | `http://localhost:4300/shop/track`: order number + phone → status (Received → Confirmed → Being prepared → Dispatched → Delivered), items and updates. Works for WhatsApp orders too |
| **Protection** | Validated input, a hidden spam trap, at most 10 orders per device every 10 minutes, and tracking only with the matching phone number |

Customer-facing status names:

| Internal status | Customer sees |
|---|---|
| New | Received |
| Needs Review | Received - being checked |
| Confirmed, Assigned | Confirmed |
| In Progress | Being prepared |
| On Hold | On hold |
| Ready / Dispatched | Dispatched |
| Completed | Delivered |
| Cancelled | Cancelled |

---

## 14. Prices and payments

**Prices.** Each product has a price per unit (Settings → Product catalogue). When an item is added to an order it
keeps the price of that moment, so changing a catalogue price later does not change orders already placed.
Operators can change the price on an order line for a special rate. Customers never set prices.

**Order amount.** Filled in automatically from the items (quantity × price). An office user can change it, for
example for a discount or delivery charge; editing the items recalculates it. If an item has no price, the amount
stays empty until someone sets it.

**Recording a payment.** On the order page, under *Payment*: amount, method (cash, UPI, bank transfer, card,
cheque, other), date received, an optional reference (UPI / UTR / cheque number) and a note. *Mark fully paid*
fills in the balance. A payment cannot be more than the balance, dated in the future, or added to a cancelled order.

| Payment status | Meaning |
|---|---|
| Unpaid | Nothing received yet |
| Partially Paid | Something received, balance still due |
| Paid | Full amount received (or the amount is zero) |

| Action | Who |
|---|---|
| Set or change the order amount | Admin, supervisor, operator. Never below what was already received |
| Record a payment | Office users, and the department handling the order (e.g. cash collected on delivery) |
| Remove a payment entered by mistake | Admin, supervisor, with a reason |

Every amount change, payment and removal is written to the audit log. The Orders page has a *Payment* filter,
and the dashboard shows the total still to collect. Customers see the order amount and payment status on the
tracking page.

**Not stored:** card numbers, CVV, UPI PINs or bank passwords. Only the reference number of a payment is kept.
