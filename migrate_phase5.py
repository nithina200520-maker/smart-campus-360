"""
PHASE 5 MIGRATION - Lost & Found AI & Notifications improvements.

Safe & non-destructive (idempotent - re-running changes nothing further):
  1. Backs up the SQLite database file before touching anything.
  2. Adds missing columns to existing tables (only if absent):
       lost_found_items   -> is_duplicate, duplicate_of_id
       lost_found_matches -> decided_by_admin_id, decided_at, rejected_reason
       notifications      -> dedup_key (+ unique index for duplicate-alert safety)
  3. Backfills dedup keys on EXISTING match notifications so future re-runs of
     the matcher can never re-notify the same historical alert. The derived key
     format mirrors the live code path (lf-match:pair:<lost>-<found>:u<user>),
     and collisions across historic rows are tolerated by keeping the first
     occurrence's key and leaving later duplicates NULL (NULL = always allowed).
  No table is dropped, no row is deleted - all existing records are preserved.

Run:  python migrate_phase5.py
"""
import shutil
from datetime import datetime
from pathlib import Path

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
    dest = backup_dir / f"smart_campus_360_pre_phase5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def add_missing_columns():
    """ALTER TABLE only for columns that do not exist yet (idempotent)."""
    from sqlalchemy import text
    plan = {
        "lost_found_items": [
            ("is_duplicate", "BOOLEAN DEFAULT 0"),
            ("duplicate_of_id", "INTEGER"),
        ],
        "lost_found_matches": [
            ("decided_by_admin_id", "INTEGER"),
            ("decided_at", "DATETIME"),
            ("rejected_reason", "VARCHAR(255)"),
        ],
        "notifications": [
            ("dedup_key", "VARCHAR(120)"),
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
        # Unique index enforcing notification idempotency (NULL keys unaffected)
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_notifications_dedup_key "
            "ON notifications (dedup_key)"))
        conn.commit()
        print("[schema] Unique index on notifications.dedup_key ensured.")


def backfill_notification_dedup_keys():
    """Derive dedup keys for historical match alerts so re-runs stay silent."""
    from sqlalchemy import text
    with db.engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, user_id, link_url FROM notifications "
            "WHERE category = 'match' AND dedup_key IS NULL ORDER BY id")).fetchall()
        pairs = conn.execute(text(
            "SELECT lost_item_id, found_item_id FROM lost_found_matches")).fetchall()
        item_users = {r[0]: r[1] for r in conn.execute(
            text("SELECT id, user_id FROM lost_found_items")).fetchall()}

        claimed_users = set()
        stamped = 0
        for lost_id, found_id in pairs:
            involved = {item_users.get(lost_id), item_users.get(found_id)}
            key = f"lf-match:pair:{lost_id}-{found_id}"
            for note_id, user_id, link_url in rows:
                if user_id not in involved:
                    continue  # this alert is unrelated to the pair
                link = link_url or ''
                if f"/item/{lost_id}" not in link and f"/item/{found_id}" not in link:
                    continue  # alert points at a different report
                full_key = f"{key}:u{user_id}"
                if full_key in claimed_users:
                    continue  # tolerate historic double-alerts: first keeps the key
                conn.execute(text("UPDATE notifications SET dedup_key = :k WHERE id = :i"),
                             {"k": full_key, "i": note_id})
                claimed_users.add(full_key)
                stamped += 1
        conn.commit()
    print(f"[dedup] {stamped} historical match notification(s) stamped with dedup keys.")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 5 MIGRATION - Lost & Found AI & Notifications ===")
        backup_database()
        db.create_all()  # future-proof: creates anything missing, never touches rows
        add_missing_columns()
        backfill_notification_dedup_keys()
        print("Phase 5 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
