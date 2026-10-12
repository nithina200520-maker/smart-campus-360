# SMART CAMPUS 360
### An AI-Powered Campus Navigation, Lost & Found, and Smart Canteen Management System
**Institutional Deployment:** Government Engineering College, Mosalehosahalli (Hassan), Karnataka, India  
**Affiliation:** Visvesvaraya Technological University (VTU) Belagavi | Approved by AICTE New Delhi  

---

## 📌 Project Overview
**Smart Campus 360** is a single integrated web platform containing three core modules:
1. **Module 1: Smart Campus Navigation**
   - Interactive 2D map canvas with zoom in/out, double-click zoom, and drag-to-pan.
   - Search directory across classrooms, laboratories, HOD chambers, offices, central library, and canteen.
   - Shortest route calculation using **A\*** (Heuristic) and **Dijkstra** graph algorithms.
   - Street View-style photographic waypoints for visual orientation.
   - Administrative map and waypoint management foundation.
2. **Module 2: AI Lost & Found**
   - Incident reporting for lost and found articles with photo upload.
   - **OpenCV visual feature vector extraction** and cosine similarity matching.
   - Automated suggestion alerts when candidate matches are discovered.
   - Item ownership claim and verification tracking.
3. **Module 3: Smart Canteen Management**
   - Daily menu catalog with live stock status and item pricing.
   - Advance order booking with time slot scheduling.
   - **Teacher-First Order Priority**: Automatic queue elevation for faculty orders.
   - Dynamic **QR Code generation** for counter pickup verification.
   - Payment simulation (UPI / Card / Cash at counter) and cancellation refund workflow.

---

## 👥 Role-Based Access Control (RBAC) Matrix

| Persona | Pre-configured Email | Default Password | Permissions & Capabilities |
| :--- | :--- | :--- | :--- |
| **Main Admin** | `admin@gechassan.ac.in` | `Admin@123` | Universal control across all 3 modules, user management, audit logs, node & photo management. |
| **Canteen Admin** | `canteen@gechassan.ac.in` | `Canteen@123` | Restricted to canteen operations: live kitchen queue, Teacher-First priority queue, QR verification, menu & stock editor. |
| **Teacher** | `teacher@gechassan.ac.in` | `Teacher@123` | Faculty access, campus navigation, lost & found, **automatic Teacher-First Priority queue** on canteen orders. |
| **Student** | `student@gechassan.ac.in` | `Student@123` | Navigation, reporting lost/found items, browsing & advance booking from canteen. |
| **Visitor** | `visitor@gechassan.ac.in` | `Visitor@123` | Public navigation, reporting found items, guest canteen pickup. |

*Note: For convenient local testing, a 1-click **"Switch Role"** pill is provided in the top navigation header and login page.*

---

## 🗂️ Complete Project Folder Structure

```
COLLEGE CAMPUS ANTIGRAVITY/
├── .env.example                       # Environment variables template
├── .env                               # Active environment configuration
├── requirements.txt                   # Python dependencies
├── run.py                             # Main application entry point
├── init_db.py                         # Database creation & sample data seeder
├── schema.sql                         # Pure MySQL 8.0 DDL schema script
├── generate_placeholders.py           # PIL script generating sample photos
├── README.md                          # Documentation and setup instructions
│
├── instance/
│   └── smart_campus_360.db            # Automatic SQLite failover database (zero-friction dev)
│
├── app/
│   ├── __init__.py                    # Flask application factory (create_app)
│   ├── config.py                      # Multi-environment configuration & database resolver
│   ├── database.py                    # SQLAlchemy instance & failover connection manager
│   ├── models.py                      # Relational ORM models for all 3 modules
│   │
│   ├── blueprints/
│   │   ├── auth/                      # Authentication, registration & RBAC
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── main/                      # Unified landing portal & about pages
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── admin/                     # Main Admin unified dashboard & users hub
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── canteen_admin/             # Canteen Admin queue & menu manager
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── navigation/                # Module 1: Map viewer & routing API
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── lost_found/                # Module 2: AI similarity & reporting
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   └── canteen/                   # Module 3: Food tray, QR checkout, orders
│   │       ├── __init__.py
│   │       └── routes.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── auth_helpers.py            # @login_required, @role_required, session helpers
│   │   ├── pathfinding.py             # A* & Dijkstra graph traversal algorithms
│   │   ├── image_matcher.py           # OpenCV color-spatial embedding & cosine matcher
│   │   └── qr_generator.py            # High-resolution QR code generator (PNG / Base64)
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css              # Custom styling, teacher priority badges, canvas map
│   │   ├── js/
│   │   │   ├── main.js                # Toast notifications & UI interactions
│   │   │   └── navigation.js          # Interactive canvas, double-click zoom, route renderer
│   │   ├── images/                    # Sample photography and dish photos
│   │   └── uploads/
│   │       ├── navigation/            # Uploaded campus waypoint photographs
│   │       ├── lost_found/            # Uploaded lost & found item photographs
│   │       ├── canteen/               # Menu item photos
│   │       └── qr_codes/              # Generated order pickup verification QR codes
│   │
│   └── templates/
│       ├── base.html                  # Master layout with responsive navbar & footer
│       ├── errors/                    # 403, 404, 500 custom error pages
│       ├── main/
│       │   ├── index.html             # Unified 3-module portal home
│       │   └── about.html             # Institutional profile & technical specs
│       ├── auth/
│       │   ├── login.html             # Login card with 1-click test credentials
│       │   ├── register.html          # Registration for Student, Teacher, Visitor
│       │   └── profile.html           # User profile & priority queue status
│       ├── admin/
│       │   ├── dashboard.html         # Main Admin command center (all modules)
│       │   └── users.html             # User role editor & account suspension
│       ├── canteen_admin/
│       │   ├── dashboard.html         # Live kitchen queue with Teacher Priority
│       │   └── menu_manage.html       # Dish catalog & stock toggle
│       ├── navigation/
│       │   └── index.html             # Module 1 interactive map & Street View modal
│       ├── lost_found/
│       │   ├── index.html             # Module 2 registry listing & search
│       │   ├── report.html            # Report item with photo upload
│       │   └── detail.html            # AI similarity matches & claim button
│       └── canteen/
│           ├── index.html             # Module 3 menu & add-to-tray
│           ├── cart.html              # Pickup time scheduler & checkout
│           ├── order_success.html     # QR code display & priority badge
│           └── my_orders.html         # User order tracking history
```

---

## 💻 Exact Windows 11 & VS Code Setup Instructions

### Step 1: Open Project in VS Code
1. Launch **Visual Studio Code**.
2. Go to **File -> Open Folder...** and select:
   `c:\Users\nithi\OneDrive\Documents\COLLEGE CAMPUS ANTIGRAVITY`
3. Open a new PowerShell terminal in VS Code:
   Press `` Ctrl + ` `` (Backtick) or go to **Terminal -> New Terminal**.

### Step 2: Verify Python Environment
Ensure Python 3.10+ is detected:
```powershell
python --version
```

### Step 3: Configure Database Connection
The application is pre-configured with a dual database connector:
1. **To use MySQL (Default target):**
   - Ensure your MySQL server service is running (`Get-Service MySQL*`).
   - Open `.env` and set your MySQL password:
     ```env
     USE_SQLITE=False
     DB_HOST=localhost
     DB_PORT=3306
     DB_USER=root
     DB_PASSWORD=your_actual_mysql_password
     DB_NAME=smart_campus_360
     ```
   - Run the initialization script to automatically create the database and seed tables:
     ```powershell
     python init_db.py
     ```
2. **Instant Zero-Friction Testing (Local SQLite Fallback):**
   - If MySQL credentials are not yet entered or MySQL is offline, the app automatically detects this and falls back to a local SQLite database in `instance/smart_campus_360.db` without crashing!
   - You can also explicitly set `USE_SQLITE=True` in `.env`.

### Step 4: Run the Application
Start the Flask development server:
```powershell
python run.py
```
Output will confirm:
```
======================================================================
  SMART CAMPUS 360 - INITIALIZING INTEGRATED PLATFORM
  Institution: Government Engineering College, Mosalehosahalli
  Location:    Hassan, Karnataka, India
======================================================================
  [✓] Module 1: Smart Campus Navigation (A*/Dijkstra & Street View)
  [✓] Module 2: AI Lost & Found (OpenCV Visual Similarity)
  [✓] Module 3: Smart Canteen (Teacher-First Priority & QR Codes)
  [✓] Server Running at: http://127.0.0.1:5000/
======================================================================
```
Open **`http://localhost:5000`** in your browser (Chrome, Edge, or Firefox).

---

## 🧪 Completed Phase 1 Milestones

1. **Integrated Directory Architecture**: Single repository containing all 3 modules with shared models, utilities, and templates.
2. **Database Engine**: Complete MySQL schema (`schema.sql`) and SQLAlchemy ORM models with seed script (`init_db.py`).
3. **Session RBAC**: 5 distinct roles (`main_admin`, `canteen_admin`, `teacher`, `student`, `visitor`) with route security decorators.
4. **Main Admin Command Center**: Unified dashboard tracking cross-module metrics, user roles, and security audit logs.
5. **Canteen Operator Hub**: Live kitchen queue sorted strictly by **Teacher-First Priority**, QR code verification, and menu/stock management.
6. **Module 1 (Navigation Foundation)**:
   - Interactive 2D map canvas with zoom in/out, reset, double-click zoom, and drag-to-pan.
   - Graph representation with nodes and distance edges.
   - A* and Dijkstra shortest-path calculations with turn-by-turn instructions.
   - Street View-style photographic waypoint popup modal.
7. **Module 2 (AI Lost & Found Foundation)**:
   - Report submission form with image file upload.
   - OpenCV multi-channel color-spatial feature vector extraction.
   - Cosine similarity matching engine recommending potential counterparts.
8. **Module 3 (Smart Canteen Foundation)**:
   - Categorized menu with live stock indicators.
   - Food tray cart and scheduled advance pickup slot selector.
   - Automated **Teacher-First Priority** assignment on checkout.
   - High-resolution pickup verification QR code generation.
   - Order cancellation and simulated refund workflow.
9. **Calibration Transparency**: Labeled sample data throughout the codebase, designed for seamless real-campus data import without rebuilding the application. 

## 🔐 Completed Phase 2 Milestones - Authentication & Role Management

1. Secure login/logout with hashed passwords, hardened sessions (2-hour lifetime, HttpOnly, SameSite) and instant session termination on account deactivation.
2. Student / Teacher / Visitor registration flows; public registration can **never** create a Main Admin.
3. Teacher verification workflow - canteen priority applies **only to verified teachers**.
4. Password reset with single-use, time-limited, constant-time-verified tokens.
5. Account activation/deactivation, role changes and every privileged action recorded in the audit trail.
6. Production lockdown of the demo role-switcher (403 + audit log outside development) and visitor masking of private contact data.
7. pytest suite (73 tests) running against an isolated throwaway database.

## 🧭 Completed Phase 3 Milestones - Smart Campus Navigation

> All Phase 3 campus content is **temporary sample data** for Government Engineering College, Mosalehosahalli (Hassan), Karnataka. No real room numbers or verified routes are invented - replace them through the admin screens or CSV import.

1. **Location Search** - classrooms, laboratories, HOD offices, administrative offices, library, canteen, corridors, staircases and hostels are searchable and filterable by building and floor.
2. **Digital Campus Map & Floor Plans** - schematic campus canvas plus uploaded per-building/per-floor digital floor plans with zoom, drag and double-click exploration.
3. **Route Calculation** - A* (heuristic) and Dijkstra executed on the node/edge graph; routes strictly follow configured walkable connections, including one-way edges.
4. **Photo Navigation** - photograph per navigation point (buildings, corridors, staircases, rooms, landmarks) uploaded by the Main Admin.
5. **Interactive Viewer** - double-click zoom-in, zoom-out, reset, drag-to-explore, full-screen campus map and full-screen photo viewing.
6. **Street View-Style Experience** - calculating a route unlocks *Start Street-View Walkthrough*: the photograph tied to each navigation point with turn-by-turn instructions; directional arrows open the photograph of every walkably connected point; previous/next connected-photograph buttons; panoramic (360°) photographs are supported via the per-node panoramic flag.
7. **Main Admin Map Manager** (`/admin/navigation/manage`, linked from the dashboard) - upload photographs, create buildings & floors, add rooms, define navigation points and connect walkable paths, manage floor plans.
8. **Data Import** - downloadable CSV templates for nodes, connections and floor plans, with bulk import (duplicate-safe, audit-logged) at `/admin/navigation/import`.
9. **New API** - `GET /navigation/api/node/<id>/connections` powers photo-to-photo street-view movement.
10. **Migration** - `python migrate_phase3.py` (automatic DB backup first; existing data preserved; idempotent).

### Testing Phase 3 in VS Code (Windows 11)

```powershell
python migrate_phase3.py          # one-time schema + sample data upgrade (backs up DB first)
python run.py                     # dev server on http://127.0.0.1:5000
python -m pytest -q               # full 73-test suite on an isolated temp database
docker compose up -d --build web  # production image on http://127.0.0.1:8080
```

1. Open **/navigation** - search "HOD", pick route *Main Gate → Sample Classroom A-102*, choose A* or Dijkstra, then click **Start Street-View Walkthrough** and follow the photos with the directional arrows (double-click to zoom, `⛶` for full screen).
2. Choose *Academic Block A / Ground Floor* filters and open the sample **floor plan** from the *Digital Map & Floor Plans* card.
3. Log in as Main Admin → Dashboard → **Manage Map & Photos** - create a node with a photo upload, connect a path, upload a floor plan, download a CSV template, re-import it, and confirm every action appears in Audit Logs.
