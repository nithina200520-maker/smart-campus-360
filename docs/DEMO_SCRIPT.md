# SMART CAMPUS 360 — COLLEGE DEMONSTRATION SCRIPT
### Government Engineering College, Mosalehosahalli (Hassan), Karnataka

**Total time:** ~35–40 minutes · **Machine:** laptop with the app running · **Network:** none required (fully local)
**Browsers:** two windows side by side works best — one signed in as the customer persona, one as the admin persona. In development mode the **role-switch pill** in the top bar makes this one click.

---

## 0. Pre-demo preparation (day before)

```powershell
python -m pytest -q            # must show: 263 passed
python run.py                  # http://127.0.0.1:5000/
```

- [ ] Fresh seeded database (run `python init_db.py` on a clean machine) — demo accounts below.
- [ ] Prepare props in a folder: 1 photo of a lost item (e.g. a bottle/wallet/keys), 1 floor-plan image, 1 food photo.
- [ ] Pre-create one **found-item report with photo** (e.g. *"Found Water Bottle [DEMO]"*) so the AI has something to match against in step 5.
- [ ] Confirm a canteen pickup slot exists **for today, ≥ 30 minutes in the future** (Canteen Admin → Slots) with remaining capacity.
- [ ] Close the terminal windows so startup logs don't flash on screen.
- [ ] Walk through this entire script once on the demo machine.

**Accounts:** Main Admin `admin@gechassan.ac.in/Admin@123` · Canteen Admin `canteen@gechassan.ac.in/Canteen@123` · Teacher `teacher@gechassan.ac.in/Teacher@123` · Student `student@gechassan.ac.in/Student@123`

> **Opening statement to the panel (say it, don't skip it):**
> *"All campus locations, items and menu data in this demonstration are clearly labelled
> SAMPLE data. Payments run through a SANDBOX gateway — no real money moves. Notifications
> are in-app. The system is deployment-ready for the college to load its verified data
> and, optionally, configure a live payment account."*

---

## Act 1 — Platform & Main Admin login (3 min)

**Step 1. Main Admin login**
1. Open `http://127.0.0.1:5000/` — point out the three-module portal.
2. **Login** → `admin@gechassan.ac.in` / `Admin@123`.
3. Land on **Dashboard** (`/admin/dashboard`): scroll through live counters — users by
   role, map nodes, open Lost & Found reports, kitchen queue, payments & refunds, recent
   audit entries.
   *Narrate:* "One account, one dashboard, every module — and every privileged action
   from this session will be written to an audit log we'll check at the end."

## Act 2 — Campus management (5 min)

**Step 2. Manage navigation data**
1. Dashboard → **Manage Map & Photos** (`/admin/navigation/manage`).
2. Create a navigation point live: name *"Demo Seminar Hall [DEMO]"*, building, floor,
   category, canvas coordinates, upload the floor-plan photo as its image.
3. Connect it with a walkable edge (distance ~25 m) to an existing node.
4. Show **Publish/Unpublish**: unpublish it → open the public map in the other window →
   the node is gone from search, map **and** routing. Re-publish.
5. Show the **CSV templates** download (nodes/edges/floor plans) — *narrate:* "the whole
   real campus is imported like this, no code changes."

## Act 3 — Navigation & photograph exploration (5 min)

**Step 3. Public user experience**
1. Switch window to **Student** login → **Navigation** (`/navigation`).
2. Search *"Central Library"*; filter by building/floor.
3. Route: *Main Gate → Central Library* — run **A***, then **Dijkstra**; compare total
   distance; read turn-by-turn hints.
4. Click **Start Street-View Walkthrough** — move point-to-point through the photographs
   using directional arrows; double-click zoom; full-screen one photo.
   *Narrate:* "routes only follow physically walkable connections, including one-way paths."

## Act 4 — Lost item reporting (4 min)

**Step 4. File a report with photo**
1. Student → **Lost & Found → Report Item**.
2. Fill: *Lost*, title "Lost Water Bottle [DEMO]", category Bottle, colour, today's date,
   location *Central Library*, description; upload the bottle photo.
3. Submit — mention the magic-byte/8 MB validation protects the server.

## Act 5 — AI matching & notifications (5 min)

**Step 5. Watch the engine work**
1. Open the new report detail — the **ranked suggestions** panel shows the pre-created
   *Found Water Bottle* with a composite score and the **factor breakdown**
   (image similarity 60% + category/colour/date/location 40%).
2. Student's **bell icon** now shows an unread match alert → open `/notifications/`.
3. Switch to **Main Admin** → **Lost & Found Center**: the same suggestion awaits an
   admin **decision** (approve/reject) — engine proposes, human disposes.
4. Back as Student → **Claim This Item** with a private proof statement
   ("brand sticker on the cap") → Admin sees the claim → **Approve** → **Record Return**
   → status *Closed*; both users notified at every step.
   *Narrate:* "similarity is decision support only — the proof statement plus admin
   verification is what returns property; contact details are masked from everyone else."

## Act 6 — Canteen menu management (3 min)

**Step 6. Canteen Admin operations**
1. Switch to **Canteen Admin** → `/canteen_admin/menu`.
2. Add/edit an item live (*"Demo Masala Tea — ₹8, stock 40"*), toggle availability →
   show the public canteen page updating instantly.
3. **Slots** page: show today's slot, capacity and the teacher-reserve note.

## Act 7 — Teacher-priority booking (4 min)

**Step 7. Faculty books first**
1. Switch to **Teacher** → Canteen → add 2 items → cart → choose the slot → checkout →
   sandbox payment → confirmation shows **PRIORITY badge**, QR token and an earlier
   estimated ready time.
2. Canteen Admin → **Dashboard**: the teacher's order sits **at the top of the kitchen
   queue** above student orders of the same slot.
   *Narrate:* "25% of every slot's capacity is reserved for verified teachers until the
   slot starts, and the kitchen sorts priority-first — students are never blocked
   permanently because reserves release at slot start."

## Act 8 — Student advance booking (4 min)

**Step 8. Regular booking path**
1. Switch to **Student** → order 1–2 items into the same slot → checkout → payment →
   **QR code** displayed; order visible in **My Orders** as *Confirmed/Pending*.
2. Canteen Admin → move the **teacher's** order first: *Preparing → Ready* — student's
   order waits behind it. The queue discipline is visible on screen.

## Act 9 — QR pickup (2 min)

**Step 9. Verify at the counter**
1. Canteen Admin → **Verify Pickup** → enter/scan the teacher's order token →
   order closes as **Collected**; teacher's bell shows the collection notification.
2. Re-submit the same token → rejected (single-use, server-side token check).

## Act 10 — Simulated undelivered order (3 min)

**Step 10. The failure path, honestly**
1. Student's order stays *Ready* but is "never collected" (do nothing with it).
2. Student → **My Orders → Request Refund** → complaint note:
   *"Order was not served at my slot."* → status becomes **Refund Requested**.

## Act 11 — Refund processing in sandbox mode (3 min)

**Step 11. Governed refund**
1. Canteen Admin dashboard → refund register shows the complaint with full order/payment
   context → **verify**, then **Authorize & Initiate Refund** (choose full amount —
   partial is available too).
2. Show the trail: *Requested → With Gateway → Refunded*, with **authorized-by**,
   timestamps and attempts — status only flips on reliable gateway confirmation.
3. Student's order now reads **Refunded**; payment record shows the refund reference.
   *Narrate:* "this is the **sandbox gateway** — the workflow, authorization and audit
   trail are production-shaped, but no real money moves. A live gateway is a
   configuration decision the college must test separately."

## Act 12 — Main Admin monitoring everything (4 min)

**Step 12. Closing the loop**
1. **Main Admin** → Dashboard: canteen counters reflect today's demo orders, refund and
   queue; Lost & Found counters show the closed case.
2. **Reports** (`/admin/reports`): Chart.js revenue, item popularity, order-status mix.
3. **Unified canteen console** (`/admin/canteen`): payment ledger + refund register —
   every rupee of the demo reconciles.
4. **Audit Logs** (`/admin/audit-logs`): filter to this session — logins, node created,
   claim decided, refunds authorized... *"every action, every actor, every IP, timestamped."*

## 13. Close (2 min)

Recap in one breath: *three real campus problems, one platform, five guarded roles,
A\*/Dijkstra routing with photo walkthrough, pretrained-network image matching with a
governed claim workflow, teacher-first canteen operations, tokenised QR pickup,
full refund trail — 263 automated tests behind every screen.*
Then state the boundaries from `docs/LIMITATIONS_AND_FUTURE.md` before questions —
panels consistently rate honest limitation slides higher than overselling.

---

## Troubleshooting during the demo

| If… | Do… |
|---|---|
| AI shows no match | Check the pre-created *Found* report is still `open`; refresh; verify both photos are real images |
| Slot not bookable | It needs ≥ 15 min lead time — create a later slot as Canteen Admin first |
| Payment page stalls | Sandbox is instant by default; someone set `PAYMENT_SANDBOX_PAYMENT_OUTCOME` — reset to `succeeded` |
| Port 5000 busy | `$env:PORT=5001; python run.py` and use `http://127.0.0.1:5001/` |
| Nerves / forgotten step | The navbar tells you where you are; every screen is 2 clicks from the dashboard |

[← Demonstration pack](PROJECT_REPORT.md)
