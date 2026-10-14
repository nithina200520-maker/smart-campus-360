# SMART CAMPUS 360 — STUDENT USER MANUAL

**Audience:** Students (role: `student`). The same instructions apply to **Visitors**
except where noted — visitors have reduced rights (see the last section).
**Sign in:** `student@gechassan.ac.in` / `Student@123` (demo) — or register with your
college email (Student account type).

---

## 1. Account & profile
* **Register** (`/auth/register`): choose *Student*, fill name, email, password,
  department, USN and semester. Your profile (`/auth/profile`) shows your role and
  canteen priority status.
* **Forgot password:** request a reset link token; the single-use token expires in 30 minutes.
* **Notifications bell** (top bar): live unread count; full history at `/notifications/`.

## 2. Campus Navigation (`/navigation`)
1. Open **Navigation** from the menu.
2. **Search** a destination (e.g. "Central Library", "CSE Dept") or filter by building/floor.
3. Pick a **From** and **To** point, choose **A\*** or **Dijkstra**, click **Find Route** —
   you get the shortest walking path drawn on the map, total distance and turn-by-turn hints.
4. Click **Start Street-View Walkthrough** to move photograph-by-photograph along the
   route using the directional arrows (double-click zooms, ⛶ gives full screen).
5. The map canvas supports zoom in/out, double-click zoom and drag-to-pan; digital
   floor plans open from the *Digital Map & Floor Plans* card.
> While the campus contains demo content a **SAMPLE DATA** banner is shown — routes are
> illustrative until the college publishes verified map data.

## 3. Lost & Found (`/lost-found`)
### Report something
1. **Lost & Found → Report Item** (`/lost-found/report`).
2. Choose **Lost** or **Found**, then fill: title, category, dominant colour, date & place,
   description, and a clear **photo** (PNG/JPG/WEBP, ≤ 8 MB).
3. Submit — the AI immediately compares your report against opposite-type reports.
   If candidates exist you'll get a **notification** and see ranked suggestions on your
   report (visible only to you and the administration).
4. Track everything under **My Reports** (`/lost-found/my-reports`).
### Claim a found item
1. Browse the public registry, open the item, click **Claim This Item**.
2. Write a **private proof statement** (details only the real owner would know — serial
   numbers, scratches, contents). It is never shown publicly.
3. Wait for the Main Admin's decision — you'll be notified on approval or rejection.
4. On approval, collect the item from the office; the admin records the return and your
   report closes with a timeline entry.
> AI similarity is **decision support only** — it is never proof of ownership.

## 4. Smart Canteen (`/canteen`)
### Order in advance
1. Open **Canteen** — browse categories with prices, photos and live **stock status**.
2. Click items to add them to your **tray**; adjust quantities in the cart (`/canteen/cart`).
3. Choose a **pickup slot** (slots show remaining capacity; bookings need ≥ 15 minutes
   lead time before the slot starts).
4. **Checkout** → pay through the simulated gateway → confirmation page
   (`/canteen/order_success`) shows your **order token QR code** and estimated ready time.
5. Track states (Pending → Confirmed → Preparing → Ready → Collected) in **My Orders**
   (`/canteen/my-orders`); each change sends a notification.
### Collect your food
Show the QR at the counter — the Canteen Admin scans/enters it and the order becomes
**Collected**. Keep your phone screen or the QR image; the code works once.
### Cancel or complain
* Before preparation starts: **Cancel** from My Orders → refund flows automatically
  through the sandbox gateway.
* Order paid but never delivered (or wrong): press **Request Refund** and record your
  complaint; the canteen team verifies, authorises and processes a full or partial refund —
  every step is visible in your order history.
> **Payments are sandbox-simulated** in this build — no real money moves.

## 5. Visitor account notes
Visitors may: navigate the campus, view the Lost & Found registry, **report found items**,
and place guest canteen pickups. Visitors may **not**: file lost-item reports with claims,
view private contact details (masked everywhere), or access any admin area.

[← Demonstration pack](../PROJECT_REPORT.md)
