# SMART CAMPUS 360 — MAIN ADMIN USER MANUAL

**Audience:** Principal / system owner (role: `main_admin`) — universal control over all
three modules, users, payments oversight and the audit trail.
**Sign in:** `admin@gechassan.ac.in` / `Admin@123` (demo).
Public registration can **never** create a Main Admin account.

---

## 1. Command Dashboard (`/admin/dashboard`)
Single screen showing live cross-module metrics: user counts by role, navigation
nodes/edges and photo coverage, open/claimed/closed Lost & Found reports, pending claims
and AI match decisions, canteen orders by state, today's slot utilisation, payment and
refund totals, and recent audit entries. Every management console is one click away.

## 2. User & role management (`/admin/users`)
* Search and list all accounts with role, department, verification and active state.
* **Verify / revoke teachers** — the *only* gate for canteen priority (O9).
* **Change role** (e.g. student → teacher after staff joining) and **activate/deactivate**
  accounts; deactivation terminates their sessions instantly.
* **Create Canteen Admin** (`/admin/create-canteen-admin`) — the only way canteen staff
  accounts come into existence; creation is audit-logged.
* Every privileged action above writes to the audit log with actor, IP and timestamp.

## 3. Campus map & navigation control (`/admin/navigation/manage`)
* **Create / edit / delete navigation points**: code, name, building, floor, category,
  canvas coordinates, description, **photo upload** (validated images) and the
  panoramic / accessible flags.
* **Connect walkable paths**: source → target, distance in metres, direction hint,
  bidirectional or one-way.
* **Publish / unpublish locations** — unpublished rooms vanish from the public map,
  search, APIs **and route finding** until officially published (Phase 8 control).
* **Floor plans**: upload per-building/per-floor digital plan images.
* **CSV bulk import** (`/admin/navigation/import`): download templates for nodes,
  connections and floor plans; imports are duplicate-safe and audit-logged.
* Sample rows carry `[SAMPLE]` names and `is_sample_data = true` — replace or unpublish
  them as verified college data is entered.

## 4. Lost & Found Center (`/admin/lost-found`)
* Review every report; filter by status (open / matched / claimed / closed).
* **Verify found items** and correct their reported location (notified to the owner).
* **AI match decisions**: approve or reject system-suggested pairings with a reason —
  admin judgement overrides the engine.
* **Claim queue**: read the claimant's private proof statement, compare with the
  reporter's details, then **approve or reject** with a decision note (both notified).
* **Record return**: physical handover sets status *closed* with `collected_at`.
* **Send targeted notification** to any user from the console (no broadcasts exist).

## 5. AI Lab — matcher tuning (`/admin/ai-lab`)
Adjust the Lost & Found engine live and re-run it on sample pairs to see factor
breakdowns before saving: minimum composite to surface (0.35), medium band (0.50),
strong match (0.70), duplicate flag threshold (0.65), suggestion limit (10).
Weights: image similarity 60% + blended context (category/colour/date/location) 40%.

## 6. Unified canteen console (`/admin/canteen`)
Cross-control for canteen operations from the admin side:
* Menu & stock: update item price, stock and availability (`/admin/canteen/item/<id>/update`).
* Full order ledger with payment status, priority flags and refund register.
* Oversight of slot configuration and teacher-priority behaviour
  (master switch `CANTEEN_TEACHER_PRIORITY_ENABLED`, reserve ratio 25%).
* Day-to-day kitchen operations (queue transitions, QR verification) remain delegated to
  the Canteen Admin role.

## 7. Payments & refunds oversight
* Every order has at most **one** payment record with a unique gateway intent id —
  double-capture is structurally impossible.
* Refunds require **explicit authorization by you or a Canteen Admin** before the
  gateway call; the trail stores complaint note, authorizer, timestamps, attempts.
* `confirm_mismatch` flags money captured but order unconfirmable — surfaced on the
  console and refundable; nothing is silently lost.
* Webhook deliveries are signature-verified and deduplicated (`webhook_events`).
* **This build runs the sandbox provider (or Stripe *test mode* if configured) — never
  claim live settlement without configuring and testing real credentials.**

## 8. Reports (`/admin/reports`)
Chart.js analytics computed live from the database: order/revenue trends, item
popularity, module usage and Lost & Found resolution statistics — all rendered from
real-time data, never cached numbers.

## 9. Audit logs (`/admin/audit-logs`)
Append-only trail of authentication, role, map, Lost & Found, canteen, payment and refund
actions — filterable by module, user and action. Use it to answer any
"who did what, when, from which IP" question.

## 10. Preparing the system for a real campus
1. Enter verified locations/photos/paths (or CSV import); **unpublish** all `[SAMPLE]` nodes.
2. Replace the demo menu, prices and slots via the canteen console.
3. Close/remove demo Lost & Found reports; review pending claims.
4. Delete or change every demo account's password; create real staff accounts.
5. Set a strong `SECRET_KEY`, configure MySQL, switch `FLASK_ENV=production`,
   serve via Docker/Gunicorn, and set real (test-then-live) payment credentials only
   after a tested go-live decision.

[← Demonstration pack](../PROJECT_REPORT.md)
