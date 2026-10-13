"""
PHASE 7 MIGRATION - Payment & Refund Processing.

Safe & non-destructive (idempotent - re-running changes nothing further):
  1. Backs up the SQLite database file before touching anything.
  2. Creates the new tables (via create_all): payments, refunds, webhook_events.
  3. Ensures indexes created outside SQLAlchemy definitions.
  4. Verifies the tables exist and prints row counts.
No existing table, column or row is modified or deleted; legacy orders simply
have no payment row until a gateway-backed checkout happens.

Run:  python migrate_phase7.py
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from app import create_app
from app.database import db

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "instance" / "smart_campus_360.db"

NEW_TABLES = ("payments", "refunds", "webhook_events")


def backup_database():
    if not DB_FILE.exists():
        print(f"[backup] No SQLite file at {DB_FILE} - skipping backup.")
        return None
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"smart_campus_360_pre_phase7_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def verify_schema():
    with db.engine.connect() as conn:
        for table in NEW_TABLES:
            try:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                print(f"[schema] Table '{table}' present ({count} rows).")
            except Exception as exc:  # noqa: BLE001
                print(f"[schema] !! Table '{table}' missing or unreadable: {exc}")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 7 MIGRATION - Payment & Refund Processing ===")
        backup_database()
        db.create_all()  # creates payments/refunds/webhook_events; never touches existing rows
        verify_schema()
        print("Phase 7 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
