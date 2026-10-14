# SMART CAMPUS 360 — CANTEEN ADMIN USER MANUAL

**Audience:** Canteen counter/kitchen staff (role: `canteen_admin`).
**Sign in:** `canteen@gechassan.ac.in` / `Canteen@123` (demo).
Accounts are created **only** by the Main Admin (`/admin/create-canteen-admin`).
Access is strictly limited to canteen operations — no other module data is visible.

---

## 1. Live kitchen queue (`/canteen_admin/dashboard`)
* All active orders sorted **Teacher-First**: verified-teacher priority orders (PRIORITY
  badge) appear above regular orders within the same slot.
* Each card shows order code, customer, items, slot, payment status, token QR state and
  the estimated ready time.
* **Advance an order through the lifecycle** with one click per transition:
  `Confirmed → Preparing → Ready for Pickup` (customer is notified at each step),
  and handle refund complaints from the same console.
* **Verify pickup** (`/canteen_admin/verify-pickup`): scan or type the customer's QR
  token — the server checks the opaque `pickup_token`, marks the order **Collected**,
  stamps `collected_at` and notifies the customer. An already-collected or cancelled
  token is rejected visibly.

## 2. Menu management (`/canteen_admin/menu`)
* Add items: name, category, description, price, stock quantity, preparation time, photo
  (validated image upload).
* Edit any item (`/canteen_admin/menu/edit/<id>`) and **toggle availability** instantly
  (sold-out switch customers see immediately on `/canteen`).
* Categories and display order are maintained here; stock decrements on confirmed orders
  and releases on cancellations — no overselling.

## 3. Pickup slots (`/canteen_admin/slots`)
* Create slots per date: name (e.g. "Lunch Break"), start–end time, **order capacity**,
  active toggle.
* Capacity governs bookings; a share (25% by default) is reserved for verified teachers
  until the slot starts, then fully released to everyone.
* Deactivate a slot (e.g. holiday, shortage) without deleting it
  (`/canteen_admin/slots/<id>/toggle`).

## 4. Refunds & undelivered orders (`/canteen_admin/dashboard` refund register)
Workflow for a complaint or an order that was never collected:
1. Customer raises **Request Refund** with a complaint note → order becomes
   *Refund Requested* and appears in your register.
2. Verify the facts (kitchen log, slot, collection state).
3. **Authorize & initiate the refund** (`/canteen_admin/orders/<id>/refund`) — full or
   **partial** amount. Nothing moves without this explicit authorization.
4. The sandbox gateway processes it: *Processing (With Gateway)* → *Succeeded* on
   reliable confirmation. Failures stay visible — **retry**
   (`/canteen_admin/refunds/<id>/retry`) keeps the audit trail with attempt counts.
5. Cancelling an order before preparation triggers the automatic refund path
   (`PAYMENT_AUTO_REFUND_ON_UNFULFILLABLE`), so money never strands on an
   unfulfillable order.
6. A rare *confirm mismatch* (payment captured, order couldn't confirm) is flagged for
   you to resolve (`/canteen_admin/orders/<id>/resolve-mismatch`).
> All gateway activity is **sandbox-simulated** in this build — refunds are recorded and
> verified exactly like real ones, but no live money moves.

## 5. Reports (`/canteen_admin/reports`)
Sales and operations analytics computed live: revenue by day, top items, order-status
distribution, cancellation/refund rate and slot utilisation — use them to plan stock and
staffing.

## 6. Boundaries of this role
* No access to user management, campus map, Lost & Found, audit logs or other modules.
* Cannot create admins or change roles.
* Every status change, refund action and menu edit you perform is written to the
  institution-wide audit log.

[← Demonstration pack](../PROJECT_REPORT.md)
