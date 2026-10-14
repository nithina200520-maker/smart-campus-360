# SMART CAMPUS 360 — INSTALLATION & SETUP GUIDE

Target machine for the demonstration: **Windows 10/11 with Python 3.10+** (works unchanged
on Linux/macOS). Two supported ways to run: **A. Local Python** (recommended for the
college demo) and **B. Docker** (reproducible deployment).

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or newer | `python --version` |
| pip | bundled with Python | |
| MySQL 8.0 | *optional* | Only for the institutional target setup; the app auto-falls back to SQLite |
| Docker Desktop | *optional* | Only for method B |
| Browser | Chrome / Edge / Firefox | Responsive UI, no plugins needed |

### 1. Install Python dependencies
From the project root (PowerShell):
```powershell
python -m pip install -r requirements.txt
```

### 2. Configure environment (optional but recommended)
Copy the template and edit:
```powershell
copy .env.example .env
```
Key variables (all have safe defaults — the app runs with **no .env at all**):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev placeholder | Session signing — **change for any real deployment** |
| `USE_SQLITE` | `False` | `True` forces SQLite; if MySQL is unreachable the app falls back automatically |
| `DB_HOST/PORT/USER/PASSWORD/NAME` | localhost:3306 root | MySQL connection |
| `PAYMENT_PROVIDER` | `sandbox` | `sandbox` = built-in simulated gateway; `stripe` = **test mode only** (startup refuses non-`sk_test_` keys) |
| `CANTEEN_TEACHER_PRIORITY_ENABLED` | `True` | Master switch for teacher-first slot reservation |
| `CANTEEN_TEACHER_RESERVE_RATIO` | `0.25` | Share of each slot's capacity reserved for verified teachers until slot start |
| `LF_MATCH_MIN_COMPOSITE` | `0.35` | Minimum AI composite score to surface a suggestion |
| `LF_STRONG_MATCH_SCORE` | `0.70` | Threshold labelled "high confidence" |
| `ENABLE_QUICK_SWITCH` | `True` (dev only) | 1-click role switcher for testing; **automatically disabled outside development** |

### 3. AI embedding model (optional, one-time)
```powershell
python download_embedding_model.py
```
Fetches the pretrained MobileNetV2 weights (~14 MB) for photographic AI matching.
**If skipped, the matcher transparently falls back to an offline HSV colour-spatial
histogram embedding** — every feature still works; image accuracy is simply lower.

---

## Method A — Run locally with Python

### A1. Initialise the database (fresh machine only)
```powershell
python init_db.py
```
* Creates all 17 tables and seeds the five demo accounts, `[SAMPLE]`-labelled navigation
  graph, demo menu, categories and pickup slots.
* Uses MySQL when configured, otherwise writes SQLite at `instance/smart_campus_360.db`.
* Safe to re-run: skips seeding when data already exists.
* If you upgraded an older database instead, run the phase migrations
  `python migrate_phase2.py` … `python migrate_phase8.py` (each backs up the DB first).

### A2. Start the development server
```powershell
python run.py
```
Open **http://127.0.0.1:5000/** — the startup banner confirms all three modules loaded.
To change port/host: `$env:PORT=5001; $env:HOST="0.0.0.0"; python run.py`
(`0.0.0.0` lets phones on the same WiFi open the site at your laptop's LAN IP.)

### A3. Verify the installation
```powershell
python -m pytest -q        # 263 tests, isolated throwaway database — demo data untouched
```
Then sign in with any demo account (see table below) and open each module.

### Demo accounts (pre-seeded by `init_db.py`)
| Role | Email | Password |
|---|---|---|
| Main Admin | `admin@gechassan.ac.in` | `Admin@123` |
| Canteen Admin | `canteen@gechassan.ac.in` | `Canteen@123` |
| Teacher (verified) | `teacher@gechassan.ac.in` | `Teacher@123` |
| Student | `student@gechassan.ac.in` | `Student@123` |
| Visitor | `visitor@gechassan.ac.in` | `Visitor@123` |

> These are **demonstration credentials only**. For any real deployment, delete or
> password-change every demo account immediately (Main Admin → Users) and set a strong
> `SECRET_KEY`.

---

## Method B — Run with Docker (production-style image)

```powershell
docker compose build web
docker compose up -d
```
* Application: **http://localhost:8080/** (Gunicorn WSGI inside the container).
* Container logs: `docker compose logs -f web` · Stop: `docker compose down`.
* The image runs the same `init_db.py` seeding on a clean volume; data persists in the
  compose volume, outside the image.

---

## Switching from sample data to real college data

1. Sign in as **Main Admin** → Dashboard → **Manage Map & Photos**.
2. Download the CSV templates (nodes, connections, floor plans), fill them with verified
   campus data, and import at **Data Import** (duplicate-safe, audit-logged), or create
   locations/paths one by one with photo uploads.
3. New rows are stored with `is_sample_data = False`; unverified demo rows can be deleted
   or **unpublished** (hidden from map, search, APIs and routing) without deletion.
4. Canteen: Canteen Admin → **Menu Manager** and **Pickup Slots** — replace demo items,
   prices and slots with the actual canteen board.
5. Lost & Found demo reports: Main Admin → **Lost & Found Center** — close or remove
   sample reports before go-live.

**Nothing in the application needs to be re-coded to go real — only data entry.**

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| Startup prints a MySQL "Access denied" notice then continues | Expected: automatic SQLite fallback. For MySQL, set `DB_PASSWORD` in `.env` and re-run `python init_db.py` |
| `Address already in use` on port 5000 | Another server is running — set `$env:PORT=5001` |
| AI matches look colour-only | Run `python download_embedding_model.py` once (offline fallback was active) |
| Upload rejected | Only true PNG/JPG/JPEG/WEBP ≤ 8 MB accepted (magic-byte validation) — rename alone won't help |
| Role-switch pill missing | Normal outside development mode — log in with the demo credentials instead |
| Payment/refund stays "With Gateway" | Sandbox async mode (`PAYMENT_SANDBOX_REFUND_OUTCOME=processing`) — finalise via the admin **Re-sync** action or the simulated webhook |
