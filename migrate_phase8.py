"""
PHASE 8 MIGRATION - Central Main Admin Dashboard.

Safe & non-destructive (idempotent - re-running changes nothing further):
  1. Backs up the SQLite database file before touching anything.
  2. Adds the navigation_nodes.is_published column (Main Admin location
     publication) if it does not exist yet, defaulting every existing
     location to PUBLISHED so the public map never loses points.
  3. create_all() for completeness (Phase 8 adds no new tables).
  4. Verifies the column and prints publication counts.
No existing rows are modified beyond the new column default.

Run:  python migrate_phase8.py
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from app import create_app
from app.database import db

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "instance" / "smart_campus_360.db"


def backup_database():
    if not DB_FILE.exists():
        print(f"[backup] No SQLite file at {DB_FILE} - skipping backup.")
        return None
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"smart_campus_360_pre_phase8_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def column_exists(table, column):
    insp = inspect(db.engine)
    return column in {c["name"] for c in insp.get_columns(table)}


def add_publication_column():
    if column_exists("navigation_nodes", "is_published"):
        print("[schema] navigation_nodes.is_published already present - skipped.")
        return
    with db.engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE navigation_nodes "
            "ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT 1"))
    print("[schema] Added navigation_nodes.is_published (existing locations published).")


def verify_schema():
    with db.engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM navigation_nodes")).scalar()
        published = conn.execute(text(
            "SELECT COUNT(*) FROM navigation_nodes WHERE is_published = 1")).scalar()
        print(f"[verify] {published}/{total} navigation locations published, "
              f"column present: {column_exists('navigation_nodes', 'is_published')}")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 8 MIGRATION - Central Main Admin Dashboard ===")
        backup_database()
        add_publication_column()
        db.create_all()
        verify_schema()
        print("Phase 8 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
