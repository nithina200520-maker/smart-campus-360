"""
PHASE 6 MIGRATION - Smart Canteen Booking.

Safe & non-destructive (idempotent - re-running changes nothing further):
  1. Backs up the SQLite database file before touching anything.
  2. Creates the new canteen_pickup_slots table (via create_all).
  3. Adds missing columns to canteen_orders (only if absent):
       slot_id, pickup_token, estimated_ready_at, confirmed_at
     plus a unique index on pickup_token (one secure QR secret per order).
  4. Seeds a sample week of realistic pickup slots ONLY when the slot table
     is still empty, so an operated canteen with real slots is never touched.
  Legacy order rows keep their 'placed' status (displayed as Pending) and
  simply have no token until re-confirmed - nothing is rewritten or deleted.

Run:  python migrate_phase6.py
"""
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from app import create_app
from app.database import db

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "instance" / "smart_campus_360.db"

# (name, start, end, capacity) template for the sample week
_SLOT_TEMPLATE = [
    ("Lunch Break", "12:30", "13:30", 60),
    ("Evening Tea Break", "16:00", "16:45", 40),
]


def backup_database():
    if not DB_FILE.exists():
        print(f"[backup] No SQLite file at {DB_FILE} - skipping backup.")
        return None
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"smart_campus_360_pre_phase6_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def add_missing_columns():
    """ALTER TABLE only for columns that do not exist yet (idempotent)."""
    from sqlalchemy import text
    plan = {
        "canteen_orders": [
            ("slot_id", "INTEGER"),
            ("pickup_token", "VARCHAR(64)"),
            ("estimated_ready_at", "DATETIME"),
            ("confirmed_at", "DATETIME"),
        ],
    }
    with db.engine.connect() as conn:
        for table, columns in plan.items():
            existing = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
            if not existing:
                print(f"[schema] {table} missing - create_all will handle it.")
                continue
            for col, ddl in columns:
                if col in existing:
                    print(f"[schema] Column {table}.{col} already exists - skipped.")
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                conn.commit()
                print(f"[schema] Added column {table}.{col}.")
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_canteen_orders_pickup_token "
            "ON canteen_orders (pickup_token)"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_canteen_orders_slot_id "
            "ON canteen_orders (slot_id)"))
        conn.commit()
        print("[schema] Indexes on canteen_orders.pickup_token / slot_id ensured.")


def seed_sample_slots():
    """Create a sample week of slots only when NO slots exist at all."""
    from app.models import CanteenPickupSlot
    if CanteenPickupSlot.query.count() > 0:
        print("[seed] Pickup slots already exist - sample seeding skipped.")
        return
    created = 0
    today = date.today()
    for day_offset in range(7):
        slot_date = today + timedelta(days=day_offset)
        for name, start, end, capacity in _SLOT_TEMPLATE:
            db.session.add(CanteenPickupSlot(
                name=name, slot_date=slot_date, start_time=start, end_time=end,
                order_capacity=capacity, is_active=True, is_sample_data=True,
            ))
            created += 1
    db.session.commit()
    print(f"[seed] Created {created} sample pickup slots (next 7 days x {len(_SLOT_TEMPLATE)} windows).")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 6 MIGRATION - Smart Canteen Booking ===")
        backup_database()
        db.create_all()  # creates canteen_pickup_slots; never touches existing rows
        add_missing_columns()
        seed_sample_slots()
        print("Phase 6 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
