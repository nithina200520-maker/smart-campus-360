# SMART CAMPUS 360 — TESTING DOCUMENTATION

**Suite:** 263 automated pytest tests · **Runtime:** typically under ~1 minute
**Isolation:** every run executes against a throwaway SQLite database in a temp location
(`SQLITE_DB_PATH`) — the demo/production database in `instance/` is **never** touched.

```powershell
python -m pytest -q              # full suite
python -m pytest tests/test_payments_phase7.py -v   # one area
```

---

## 1. Test inventory by area

| File | Tests | Covers |
|---|---:|---|
| `test_auth.py` | 15 | Registration (all public roles), login/logout, hashed passwords, session hardening, admin-never-public, deactivated-account lockout |
| `test_password_reset.py` | 8 | Reset token issue, single-use, 30-min expiry, constant-time verification, reuse rejection |
| `test_rbac.py` | 11 | Route-level access matrix across all 5 roles; 403s; role-switch lockdown outside development |
| `test_admin_management.py` | 7 | Teacher verify/revoke, role change, account toggle, Canteen Admin creation, audit entries |
| `test_navigation_phase3.py` | 21 | Node/edge CRUD, photo upload validation, A* vs Dijkstra equivalence, one-way edges, unreachable routes, street-view connection API, CSV import duplicate-safety, publish/unpublish visibility |
| `test_lost_found_phase4.py` | 29 | Report + image magic-byte validation, embedding storage, composite ranking factors, claim proof rules (own/dupe/self-claim blocks), admin approve/reject/record-return, targeted notifications, visitor/contact masking |
| `test_lost_found_phase5.py` | 32 | MobileNetV2/HSV embedding modes, duplicate-report detection, notification dedup keys, match decision workflow, AI Lab threshold tuning, match visibility authorisation |
| `test_canteen_phase6.py` | 34 | Menu/stock lifecycle, slot capacity & lead-time rules, cart→order flow, 9-state order lifecycle, QR token issuance & one-time verification, teacher-first allocation maths, cancellation stock release |
| `test_teacher_priority.py` | 5 | Verified-teacher-only priority, 25% reserve maths, reserve release at slot start, unverified teacher treated as regular |
| `test_payments_phase7.py` | 25 | Sandbox intent lifecycle, unique intent id (no double capture), HMAC webhook verification + replay dedup, auto-confirm, full/partial refund authorization trail, failure → retry, confirm-mismatch handling, Stripe test-mode key guard |
| `test_admin_phase8.py` | 21 | Unified dashboard metrics, location publication gating (map/API/routing), canteen console controls, payment ledger, refund & complaint register, RBAC isolation proofs |
| `test_integration_phase9.py` | 16 | Cross-module E2E: register → report → match → claim → return; browse → order → pay → ready → QR collect → refund; notification chains through one session |
| `test_system_phase10.py` | 33 | System hardening: SQLite foreign-key enforcement, upload abuse rejection, CSV savepoint isolation, flash messaging, headless `create_admin.py`, responsive report tables, audit coverage |
| **Total** | **263** | |

## 2. Testing strategy per phase
Each delivery phase (2→10) added its own regression suite before the next phase started;
the full 263-test gate must pass for every phase commit. Unit tests target services
(`pathfinding`, `image_matcher`, `canteen_booking`, `payment_service`), functional tests
drive Flask route flows through the test client, and integration tests walk complete
multi-module journeys per persona.

## 3. AI matcher evaluation (measured, not claimed)
An offline evaluation harness (`evaluate_matcher.py` + `evaluation/lost_found_dataset/`)
scores the matcher on a labelled image dataset (8 queries × 4 categories vs 12-image gallery):

| Metric | Result (this dataset only) |
|---|---|
| Precision@1 | 1.000 |
| Hit@3 / Hit@5 | 1.000 |
| MRR | 1.000 |
| Threshold sweep | top-1 correct at every min-composite from 0.35–0.75 |

> These figures describe **only the small controlled evaluation dataset** (rendered
> sample images). They are **not** a general accuracy claim for real campus photographs;
> production accuracy depends on image quality, viewpoint and lighting. Full report:
> `evaluation/lost_found_dataset/evaluation_report.md`.

## 4. Manual demonstration verification
Before going on stage, walk through [DEMO_SCRIPT.md](DEMO_SCRIPT.md) end-to-end on the
exact demo machine — every step is designed to mirror flows that the automated suite
already proves.

## 5. Security checks included
* Passwords never stored or logged in plaintext; reset tokens constant-time compared.
* Uploads validated by magic bytes (not extension), size-capped, filename-sanitised.
* Session cookie HttpOnly + SameSite; production forces Secure; 2-hour lifetime.
* RBAC verified per route (positive **and** negative tests); visitors see masked contacts.
* Payment state changes only from backend-verified events; webhook signature + replay guard.
* Quick role-switcher (dev convenience) returns 403 + audit log outside development.
