"""
PHASE 4 MIGRATION - AI Lost & Found enhancements.

Safe & non-destructive (idempotent - re-running changes nothing further):
  1. Backs up the SQLite database file before touching anything.
  2. Adds missing columns to existing tables (only if absent):
       lost_found_items  -> color_hint, resolution_note
       lost_found_matches-> composite_score, factors
  3. Creates the new tables (via SQLAlchemy create_all, existing tables untouched):
       lost_found_claims, notifications
  4. Seeds SAMPLE demonstration data so the Phase 4 workflow is visible immediately:
       colour hints on the demo reports, one pending ownership claim,
       and the matching in-app notifications. Real campus data is used once
       imported; nothing here invents verified ownership.

Run:  python migrate_phase4.py
"""
import shutil
from datetime import datetime
from pathlib import Path

from app import create_app
from app.database import db
from app.models import LostFoundItem, LostFoundClaim, Notification, User

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "instance" / "smart_campus_360.db"


def backup_database():
    if not DB_FILE.exists():
        print(f"[backup] No SQLite file at {DB_FILE} - skipping backup.")
        return None
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"smart_campus_360_pre_phase4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def add_missing_columns():
    """ALTER TABLE only for columns that do not exist yet (idempotent)."""
    from sqlalchemy import text
    plan = {
        "lost_found_items": [
            ("color_hint", "VARCHAR(30)"),
            ("resolution_note", "TEXT"),
        ],
        "lost_found_matches": [
            ("composite_score", "FLOAT"),
            ("factors", "TEXT"),
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


def seed_color_hints():
    """Fill contextual colour only where empty - never overwrites real data."""
    hints = {
        "Casio FX-991EX Scientific Calculator [SAMPLE]": "Black",
        "Casio Scientific Calculator Found [SAMPLE]": "Black",
        "Blue Steel Water Bottle [SAMPLE]": "Blue",
    }
    updated = 0
    for title, colour in hints.items():
        item = LostFoundItem.query.filter_by(title=title).first()
        if item and not item.color_hint:
            item.color_hint = colour
            updated += 1
    db.session.commit()
    print(f"[colour] {updated} sample colour hint(s) set.")


def seed_sample_claim_and_notifications():
    """Create one SAMPLE pending claim + its targeted notifications for a live demo."""
    if LostFoundClaim.query.first():
        print("[claims] Sample claims already present - skipping seed.")
        return

    # Reporter owns the 'found' calculator; a different user claims it.
    found_calc = LostFoundItem.query.filter_by(
        title="Casio Scientific Calculator Found [SAMPLE]").first()
    if not found_calc:
        print("[claims] Demo 'found' item not present - skipping claim seed.")
        return

    claimant = (User.query.filter(User.id != found_calc.user_id,
                                  User.role.in_(["student", "teacher"]),
                                  User.is_active == True).first())  # noqa: E712
    if not claimant:
        print("[claims] No eligible demo claimant user found - skipping.")
        return

    claim = LostFoundClaim(
        item_id=found_calc.id,
        claimant_id=claimant.id,
        proof_statement=("[SAMPLE] This is my Casio FX-991EX. It has a yellow sticker on the "
                         "back and my USN 4GH22CS054 scratched into the battery cover."),
        status="pending",
    )
    db.session.add(claim)
    found_calc.status = "claimed"
    found_calc.claimed_by_user_id = claimant.id
    db.session.flush()

    Notification.notify(
        found_calc.user_id,
        title=f"Someone claimed the '{found_calc.title}' you reported",
        message=("A claim was submitted for the item you reported. Campus administration will "
                 "verify ownership before any handover. Please keep the physical item secure."),
        category="claim",
        link_url=f"/lost-found/item/{found_calc.id}",
    )
    for admin in User.query.filter_by(role="main_admin", is_active=True).all():
        Notification.notify(
            admin.id,
            title="New ownership claim awaiting verification",
            message=(f"User '{claimant.full_name}' claimed '{found_calc.title}'. "
                     "Review the private proof statement and verify or reject."),
            category="claim",
            link_url="/admin/lost-found",
        )
    db.session.commit()
    print(f"[claims] Seeded 1 sample pending claim by '{claimant.full_name}' + notifications.")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 4 MIGRATION - AI Lost & Found ===")
        backup_database()
        # Creates the two brand-new tables; existing tables are left intact.
        db.create_all()
        add_missing_columns()
        seed_color_hints()
        seed_sample_claim_and_notifications()
        print("Phase 4 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
