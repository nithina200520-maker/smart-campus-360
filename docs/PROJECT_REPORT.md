# SMART CAMPUS 360 — PROJECT REPORT
### An AI-Powered Campus Navigation, Lost & Found and Smart Canteen Management System

**Institution:** Government Engineering College, Mosalehosahalli (Hassan), Karnataka, India
**Affiliation:** Visvesvaraya Technological University (VTU), Belagavi | Approved by AICTE, New Delhi
**Document set:** Project Report (this file) · [Installation](INSTALLATION.md) · [Manuals](manuals/) · [Testing](TESTING.md) · [Limitations & Future Scope](LIMITATIONS_AND_FUTURE.md) · [Demonstration Script](DEMO_SCRIPT.md)

---

## 1. Abstract

Smart Campus 360 is a single integrated web platform that digitises three everyday campus
problems for Government Engineering College, Mosalehosahalli:

1. **Finding your way around campus** — visitors and new students waste time locating rooms,
   offices and laboratories. The platform models the campus as a walkable graph and computes
   shortest routes with the **A\*** and **Dijkstra** algorithms, enhanced with a
   Street-View-style photographic walkthrough of every navigation point.
2. **Recovering lost belongings** — manual notice-boards are slow and unreliable. Every
   report's photograph is converted into a **pretrained deep-learning image embedding**
   (MobileNetV2 via OpenCV DNN) and matched against all opposite-type reports using
   **cosine similarity blended with category, colour, date and location context**.
   Suggestions, claims, verifications and returns run through a governed workflow with
   in-app notifications.
3. **Booking canteen food without queues** — students and faculty pre-order into capacity-
   limited pickup **slots**. Verified **teachers automatically receive queue priority**
   (reserved slot capacity + top-of-queue at the kitchen counter). Pickup is verified with a
   **tokenised QR code**, and every order carries a full **payment → cancellation → refund**
   lifecycle through a sandbox payment gateway abstraction that is API-compatible with
   Stripe test mode.

The system enforces **five role-based personas** (Main Admin, Canteen Admin, Teacher,
Student, Visitor), records every privileged action in an **audit trail**, and was built and
verified through ten incremental delivery phases with an automated suite of **263 pytest
tests**. All campus content shipped with the code is **clearly labelled sample data**
(`[SAMPLE]` names and `is_sample_data` database flags) so real college data can be imported
without any code change.

---

## 2. Problem Statement

Engineering campuses with large, multi-building layouts and a high footfall of students,
staff and visitors face three recurring, unmanaged problems:

* **Wayfinding:** New students, visiting parents and guests cannot independently locate
  classrooms, laboratories, HOD chambers and offices; no digital map, route guidance or
  visual reference exists.
* **Lost & Found:** Lost belongings are handled through informal word-of-mouth and paper
  notices. There is no central registry, no way to visually match a lost item with found
  items, and no secure handover verification — leading to delayed reunions and fraudulent
  claims.
* **Canteen queues:** Physical counter queues during short breaks waste faculty time
  (teachers must attend the next period), cause over-preparation or stock-outs, and offer
  no advance booking, order tracking, payment record or refund mechanism.

**The problem addressed by this project is:** to design and build one secure, role-based,
AI-assisted web platform that provides campus navigation with visual route guidance,
image-based intelligent Lost & Found matching, and queue-less canteen pre-ordering with
teacher priority and verifiable pickup — deployable at Government Engineering College,
Mosalehosahalli with sample data replaceable by verified campus data.

---

## 3. Objectives

| # | Objective | Delivered As |
|---|-----------|--------------|
| O1 | Provide a searchable digital directory of all campus locations | Location search with building/floor/category filters (`/navigation`) |
| O2 | Compute shortest walking routes between any two campus points | A\* (heuristic) and Dijkstra on the node/edge graph (`POST /navigation/api/route`) with turn-by-turn instructions |
| O3 | Give visual orientation, not just abstract maps | Street-View-style photo walkthrough between walkably connected points; panoramic photo support; uploaded digital floor plans |
| O4 | Enable reporting of lost and found articles with photographs | Validated photo uploads (magic-byte checks, 8 MB cap) at `/lost-found/report` |
| O5 | Automatically suggest likely matches between lost and found items | MobileNetV2 image embeddings + cosine similarity, multi-factor ranking (image 60% / blended category, colour, date, location context 40%) |
| O6 | Alert users about matches and status changes | Targeted in-app notifications with unread-count bell and dedup keys (never broadcast, never duplicated) |
| O7 | Prevent fraudulent ownership claims | Private proof-statement claims → Main Admin verification → recorded return; contact details masked from non-owners |
| O8 | Allow advance canteen ordering with controlled kitchen load | Capacity-limited pickup slots, minimum lead time, live stock, estimated ready time |
| O9 | Guarantee faculty time priority in the canteen queue | Teacher-first: reserved slot capacity (25% until slot start) + priority-sorted kitchen queue for **verified** teachers only |
| O10 | Ensure food is handed to the right person | Per-order tokenised QR pickup code verified by the Canteen Admin |
| O11 | Manage money honestly: payment, cancellation, refund | Sandbox gateway abstraction (Stripe-test-mode compatible), signed webhooks with exactly-once dedup, full/partial refund workflow with explicit admin authorization |
| O12 | Enforce least-privilege access and accountability | 5-role RBAC with route decorators, hashed passwords, hardened sessions, full audit log |
| O13 | Keep sample data separable from real college data | `is_sample_data` flags, `[SAMPLE]` labels, CSV import templates, admin management screens |
| O14 | Prove correctness with automated testing | 263-test pytest suite on an isolated throwaway database; per-phase regression gates |

---

## 4. Proposed System

Smart Campus 360 replaces three disconnected manual processes with one Flask web
application sharing a single database, one authentication layer and one notification system:

* **Unified portal (`/`)** — a landing page exposing all three modules; every page is
  protected by role decorators, so each persona sees only what they are entitled to.
* **Module 1 — Smart Campus Navigation:** the Main Admin maintains buildings, rooms,
  navigation points, walkable edges (with distances and one-way rules) and photographs.
  Users search a destination, pick A\* or Dijkstra, and receive a distance-minimised route
  with turn-by-turn direction hints; they can then "walk" the route photograph by photograph.
* **Module 2 — AI Lost & Found:** a report (lost or found) with a photo is embedded by a
  pretrained MobileNetV2 network running locally through OpenCV DNN (with a documented
  offline HSV-histogram fallback). New reports are instantly compared against all
  opposite-type open reports; the top ranked candidates are stored with a transparent
  per-factor score breakdown. Owners claim with a private proof statement; the Main Admin
  arbitrates and records the physical handover.
* **Module 3 — Smart Canteen:** the Canteen Admin curates the menu, stock and pickup slots.
  Customers build a tray, choose a slot (teacher-reserved capacity applies), pay through
  the sandbox gateway, and receive a QR token. The kitchen works a queue sorted
  teacher-first; at the counter the QR is scanned/entered and verified server-side against
  the opaque token. Undelivered or cancelled orders flow through a complaint →
  authorization → gateway refund → confirmation trail.
* **Administration layer:** the Main Admin monitors every module from one dashboard
  (live counts, charts), manages users/roles/teacher verification, publishes or unpub-
  lishes locations, tunes the AI matcher thresholds in an AI Lab console, reviews audit
  logs and generates reports.

---

## 5. System Architecture

### 5.1 Architectural style
Classic **3-tier Model–View–Controller** implemented as a Flask **application factory**
(`create_app`) with **blueprints** per bounded context, server-rendered **Jinja2**
templates, progressive vanilla-JS front-ends, and a **SQLAlchemy ORM** data layer.

```
┌─────────────────────────────── Browser (any device) ───────────────────────────────┐
│  Portal · Navigation map (canvas JS) · Lost & Found forms · Canteen tray/QR · Admin │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       │ HTTP (session cookie: HttpOnly, SameSite=Lax)
┌──────────────────────────────────────▼──────────────────────────────────────────────┐
│                     Flask Application  (run.py → app.create_app)                     │
│                                                                                      │
│  Blueprints (controllers)          Utils (services)               Security            │
│  ├─ main        portal/about       ├─ pathfinding.py  A*/Dijkstra ├─ @login_required  │
│  ├─ auth        RBAC sessions      ├─ image_matcher.py MobileNetV2│  @role_required   │
│  ├─ navigation  map + JSON APIs    ├─ qr_generator.py tokenised QR│  hashed passwords │
│  ├─ lost_found  reports/AI/claims  ├─ canteen_booking.py slot &   ├─ audit logging    │
│  ├─ canteen     cart/checkout/refund│   teacher-first allocation  ├─ session          │
│  ├─ canteen_admin queue/menu/slots ├─ payment_service.py intent &│   hardening       │
│  ├─ admin       dashboards/controls│   refund lifecycle           └─ visitor masking  │
│  └─ notifications bell/history     ├─ payment_providers.py sandbox │ Stripe(test)     │
│                                    └─ sample_navigation_data.py     └─ webhook HMAC   │
│                                                                                      │
│  Models (17 SQLAlchemy tables)  ·  Jinja2 templates  ·  static CSS/JS/uploads        │
└───────────┬──────────────────────────────────────────────┬───────────────────────────┘
            │                                              │
   ┌────────▼─────────┐  auto-failover (dev)     ┌─────────▼──────────┐
   │  MySQL 8.0 (DDL: │ ◄───────────────────────►│  SQLite fallback   │
   │  schema.sql)     │      same ORM models     │  instance/*.db     │
   └──────────────────┘                          └────────────────────┘

   External (optional, test-mode only): Stripe API · Local OpenCV DNN model file
   Deployment: Docker (compose.yaml, Gunicorn) or `python run.py` dev server
```

### 5.2 Key design decisions
| Decision | Rationale |
|---|---|
| Blueprint-per-module | Independent teams/phases; shared auth & models; RBAC enforced per route |
| Dual-engine DB (MySQL ⇄ SQLite auto-failover) | College target is MySQL; zero-friction demo on any laptop without MySQL installed |
| Pretrained MobileNetV2 embeddings, local OpenCV DNN | No training data or GPU needed; deterministic offline operation; graceful HSV fallback documented |
| Composite ranking (image 60% + context 40%) | Images alone misrank identical-looking objects; colour/category/date/location context reduces false positives |
| Tokenised QR (`pickup_token` secret, code only in DB) | A photographed QR cannot be reused for another order; verification is server-side |
| Teacher reserve released at slot start | Faculty priority without indefinitely starving students |
| Payment abstraction with unique intent ids + webhook dedup table | Same transaction can never be captured twice; exactly-once business logic |
| Money state changes only from backend-verified events | Browser claims are never trusted for paid/refunded states |
| `is_sample_data` + `[SAMPLE]` labels everywhere | Real-vs-demo data separation is a schema property, not a convention |

---

## 6. Module Descriptions

### 6.1 Authentication & RBAC (`/auth`)
* Register (student/teacher/visitor — public registration can **never** create an admin),
  login, logout, forgot/reset password (single-use, 30-minute, constant-time-compared tokens).
* Passwords hashed via Werkzeug; sessions hardened (2-hour lifetime, HttpOnly, SameSite).
* Deactivating a user terminates their access instantly; all privileged actions are audit-logged.
* Teacher verification: canteen priority applies **only** to Main-Admin-verified teachers.

### 6.2 Module 1 — Smart Campus Navigation (`/navigation`)
* Searchable location directory (classrooms, labs, offices, library, canteen, hostels) with
  building/floor filters; JSON APIs: `/api/nodes`, `/api/route` (POST), `/api/node/<id>`,
  `/api/node/<id>/connections`.
* Interactive 2D canvas map: zoom, double-click zoom, drag-to-pan, full-screen.
* Route calculation with **A\*** and **Dijkstra** honouring edge distances and one-way
  connections; turn-by-turn direction hints.
* Street-View walkthrough: photographs per navigation point, directional movement only
  along walkable edges, panoramic flag support, uploaded per-building/floor digital plans.
* Main Admin map manager: nodes/edges/floor-plan CRUD with photo upload, publish/unpublish
  (unpublished points vanish from public map, APIs and routing), CSV template download and
  duplicate-safe bulk import.

### 6.3 Module 2 — AI Lost & Found (`/lost-found`)
* Report lost/found items: photo (magic-byte validated, ≤8 MB), category, colour hint,
  date, campus location, description.
* AI engine: MobileNetV2 embedding → cosine similarity vs opposite-type reports →
  composite score with per-factor breakdown; tunable thresholds (min 0.35 surface,
  0.50 medium, 0.70 strong) adjustable by the Main Admin in the AI Lab (`/admin/ai-lab`).
* Duplicate-report detection flags re-reported items above 0.65 composite.
* Match list visible **only** to the report owner and Main Admin.
* Claim → verify → return workflow with private proof statements, dispute notes,
  `collected_at` return record; targeted notifications at every transition (dedup keys).
* Main Admin Lost & Found Center (`/admin/lost-found`): review, verify, decide claims and
  suggested matches, update locations, record returns, send targeted notifications.

### 6.4 Module 3 — Smart Canteen (`/canteen`, `/canteen_admin`)
* Daily menu by category with live stock, prices, photos; Canteen Admin edits items,
  toggles availability, manages pickup slots (capacity, active flag).
* Cart → slot selection (minimum 15-min lead time) → checkout: teacher-first capacity
  reservation (25% per slot until slot start), auto-confirm, estimated ready time,
  payment via sandbox gateway, tokenised QR issued.
* Order lifecycle (9 states): pending → confirmed → preparing → ready → collected, plus
  cancelled / refund requested / processing / refunded; customer tracking at `/canteen/my-orders`.
* Kitchen queue sorted **verified-teachers first**; QR verification at counter
  (`/canteen_admin/verify-pickup`); status transitions notify the customer.
* Payments & refunds (Phase 7): one payment per order with unique gateway intent id;
  signed webhooks (HMAC, 5-min tolerance) recorded once in `webhook_events`; complaint →
  verification → **explicit admin authorization** → gateway refund → reliable confirmation;
  partial refunds; retry on failure; mismatch flag never loses money.

### 6.5 Notifications (`/notifications`)
In-app, targeted-only (never broadcast): matches, claims, decisions, returns, order status,
refunds. Navbar bell shows live unread count; mark-read / mark-all-read supported.

### 6.6 Main Admin Dashboard (`/admin`)
Cross-module command centre: live metrics from all modules, user & role management,
Canteen Admin creation, teacher verification/revocation, account suspension, unified
canteen console, map & photo manager, Lost & Found center, Chart.js reports
(`/admin/reports`), AI Lab, audit logs (`/admin/audit-logs`).

---

## 7. Database Documentation

**Engines:** MySQL 8.0 (target, DDL in `schema.sql`) · SQLite (automatic dev fallback).
**17 tables** via SQLAlchemy ORM (`app/models.py`). Foreign keys enforced (Phase 10).

### 7.1 Entity relationship overview (core)
```
User ─┬─< LostFoundItem (reporter)         User ─┬─< CanteenOrder (customer)
      ├─< LostFoundItem.claimed_by / verified_by      ├─< Payment (1:1 per order)
      ├─< LostFoundClaim (claimant)        CanteenOrder ─┬─< CanteenOrderItem >─ CanteenItem >─ CanteenCategory
      ├─< Notification (targeted)          │             ├─< Refund (full/partial trail)
      ├─< AuditLog                         │             └─→ CanteenPickupSlot (slot_id)
      └─ role: main_admin|canteen_admin|teacher|student|visitor
                                           Payment ─< Refund, ─< WebhookEvent (by provider event_id)
NavigationNode ─< NavigationEdge (source/target, directed or bidirectional)
NavigationNode ─< LostFoundItem.location_reported (by name), CampusFloorPlan (by building/floor)
```

### 7.2 Table dictionary
| Table | Purpose | Key columns |
|---|---|---|
| `users` | All 5 personas | email (unique), password_hash, role, department, usn_or_emp_id, semester, is_verified (teacher), is_active, reset_token(+expiry) |
| `navigation_nodes` | Campus locations / POIs | node_code (unique), name, building, floor, category, x/y canvas coords, photo_url, is_panoramic, **is_sample_data**, is_published |
| `navigation_edges` | Walkable connections | source/target node FK, distance_meters, direction_hint, is_bidirectional, **is_sample_data** |
| `campus_floor_plans` | Uploaded floor-plan images | building, floor, image_url, **is_sample_data** |
| `lost_found_items` | Lost or found reports | user_id FK, report_type (lost/found), title, category, location_reported, date_time_reported, photo_url, image_feature_vector (JSON `{model,vector}`), color_hint, status (open/matched/claimed/closed), claimed_by_user_id, verified_by_admin_id, collected_at, is_duplicate/duplicate_of_id |
| `lost_found_matches` | AI-suggested pairings | lost/found item FKs, similarity_score, composite_score, factors (JSON breakdown), status, decided_by_admin_id, rejected_reason |
| `lost_found_claims` | Ownership claims | item FK, claimant FK, proof_statement (private), status (pending/approved/rejected), decision_note |
| `notifications` | Targeted in-app alerts | user FK, title, message, category, link_url, is_read, **dedup_key (unique)** |
| `canteen_categories` | Menu sections | name (unique), display_order, is_active |
| `canteen_items` | Menu items | category FK, name, price, stock_quantity, is_available, preparation_time_mins, photo_url |
| `canteen_pickup_slots` | Bookable slots | name, slot_date, start/end time, order_capacity, is_active, **is_sample_data** |
| `canteen_orders` | Pre-orders | order_code (unique), user FK, user_role_at_order, **is_priority** (teacher), slot FK, pickup_token (unique QR secret), estimated_ready_at, order_status (9-state), payment_status, total_amount, qr_code_path, refund_reason |
| `canteen_order_items` | Order line items | order/item FKs, item_name, unit_price, quantity, subtotal |
| `payments` | Gateway record per order | order FK **unique** (1:1), provider (sandbox/stripe), intent_id **unique**, client_secret, amount, currency, status lifecycle, refunded_amount, confirm_mismatch |
| `refunds` | Refund trail | refund_reference (unique), payment/order FKs, provider_refund_id **unique**, amount, is_partial, status (requested/processing/succeeded/failed), complaint_note, requested_by, **authorized_by**, attempts |
| `webhook_events` | Exactly-once webhook guard | provider, event_id **unique**, event_type, payload, status (processed/ignored/failed) |
| `audit_logs` | Accountability | user FK, action, module (AUTH/NAVIGATION/LOST_FOUND/CANTEEN/ADMIN), details, ip_address, timestamp |

### 7.3 Sample-data separation
* `is_sample_data` boolean on navigation nodes, edges, floor plans and pickup slots;
  all seeded names carry a `[SAMPLE]` suffix (e.g. *"Main Entrance & Security Gate [SAMPLE]"*).
* The public map and search display a visible **SAMPLE DATA** banner while any sample rows exist.
* Real campus data enters only through the Main Admin screens or CSV import (duplicate-safe,
  audit-logged) and is stored with `is_sample_data = False` — replacing, never mixing with, demo rows.
* The live database lives in `instance/` which is excluded from Git by `.gitignore`;
  test runs use an isolated throwaway database file and never touch demo data.

---

## 8. Technology Stack

| Layer | Technology | Used for |
|---|---|---|
| Language | Python 3.10+ | Application core |
| Web framework | Flask (app factory + blueprints) | Routing, sessions, RBAC, templates |
| Templating | Jinja2 + vanilla JS + custom CSS | Server-rendered UI, canvas map, toasts |
| ORM | SQLAlchemy (Flask-SQLAlchemy) | All 17 tables, migrations via scripts |
| Primary DB | MySQL 8.0 (PyMySQL driver) | Institutional deployment target (`schema.sql`) |
| Dev DB | SQLite (automatic failover) | Zero-friction demo on any machine |
| AI / CV | OpenCV DNN + pretrained **MobileNetV2** (ImageNet weights, fetched once by `download_embedding_model.py`); HSV colour-spatial histogram fallback | Lost & Found image embeddings |
| Matching math | Cosine similarity + weighted multi-factor composite | AI suggestions & duplicate detection |
| Graph algorithms | A\* (heuristic) & Dijkstra (pure Python) | Campus shortest routes |
| QR | `qrcode` + Pillow, server-side token secrets | Pickup verification |
| Payments | Sandbox deterministic gateway abstraction, Stripe-SDK-compatible interface (**test-mode `sk_test_` enforced at startup**) | Orders, webhooks (HMAC-signed), refunds |
| Security | Werkzeug password hashing, `secrets` tokens, constant-time comparison, HttpOnly/SameSite cookies | Auth & sessions |
| Charts | Chart.js | Admin/Canteen Admin reports |
| Testing | pytest (263 tests), isolated temp DB | Regression & RBAC proofs |
| Containerisation | Docker + docker-compose, Gunicorn WSGI | Reproducible deployment |
| Docs tooling | Markdown in `docs/`, CSV import templates | Demonstration pack |
