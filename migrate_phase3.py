"""
PHASE 3 MIGRATION - Smart Campus Navigation enhancements.

Safe & non-destructive:
  1. Backs up the SQLite database file before touching anything.
  2. Adds the `is_panoramic` column to navigation_nodes (only if missing).
  3. Creates the new `campus_floor_plans` table (CREATE IF NOT EXISTS via SQLAlchemy).
  4. Seeds additional SAMPLE navigation points (classrooms, HOD offices,
     corridors, staircase, hostel), their walkable connections and sample
     floor plans - every existing record is left untouched.

Run:  python migrate_phase3.py
"""
import shutil
from datetime import datetime
from pathlib import Path

from app import create_app
from app.database import db
from app.models import NavigationNode, NavigationEdge, CampusFloorPlan
from app.utils.sample_navigation_data import (
    PHASE3_SAMPLE_NODES, PHASE3_SAMPLE_EDGES, PHASE3_SAMPLE_FLOOR_PLANS
)

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "instance" / "smart_campus_360.db"


def backup_database():
    if not DB_FILE.exists():
        print(f"[backup] No SQLite file at {DB_FILE} - skipping backup.")
        return None
    BACKUP_DIR = BASE_DIR / "backups"
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"smart_campus_360_pre_phase3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_FILE, dest)
    print(f"[backup] Database backed up to {dest.name}")
    return dest


def add_is_panoramic_column():
    """ALTER TABLE only when the column does not exist yet (idempotent)."""
    from sqlalchemy import text
    with db.engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(navigation_nodes)")).fetchall()
        cols = [r[1] for r in rows]
        if not cols:
            print("[schema] navigation_nodes table missing - create_all will handle it.")
            return
        if "is_panoramic" in cols:
            print("[schema] Column navigation_nodes.is_panoramic already exists - skipped.")
            return
        conn.execute(text("ALTER TABLE navigation_nodes ADD COLUMN is_panoramic BOOLEAN DEFAULT 0 NOT NULL"))
        conn.commit()
    print("[schema] Added column navigation_nodes.is_panoramic.")


def seed_phase3_nodes():
    created = 0
    for spec in PHASE3_SAMPLE_NODES:
        if NavigationNode.query.filter_by(node_code=spec["node_code"]).first():
            continue
        db.session.add(NavigationNode(**spec, is_accessible=True, is_sample_data=True))
        created += 1
    db.session.commit()
    print(f"[nodes] {created} new sample navigation point(s) added.")


def seed_phase3_edges():
    node_map = {n.node_code: n.id for n in NavigationNode.query.all()}
    created = 0
    for src_code, dst_code, distance, hint in PHASE3_SAMPLE_EDGES:
        src, dst = node_map.get(src_code), node_map.get(dst_code)
        if not src or not dst:
            print(f"[edges] Skipping {src_code}->{dst_code}: unknown node.")
            continue
        exists = NavigationEdge.query.filter(
            ((NavigationEdge.source_node_id == src) & (NavigationEdge.target_node_id == dst)) |
            ((NavigationEdge.source_node_id == dst) & (NavigationEdge.target_node_id == src))
        ).first()
        if exists:
            continue
        db.session.add(NavigationEdge(
            source_node_id=src, target_node_id=dst, distance_meters=distance,
            direction_hint=hint, is_bidirectional=True, is_sample_data=True))
        created += 1
    db.session.commit()
    print(f"[edges] {created} new sample walkable connection(s) added.")


def seed_phase3_floor_plans():
    created = 0
    for spec in PHASE3_SAMPLE_FLOOR_PLANS:
        exists = CampusFloorPlan.query.filter_by(
            building=spec["building"], floor=spec["floor"], title=spec["title"]).first()
        if exists:
            continue
        db.session.add(CampusFloorPlan(**spec))
        created += 1
    db.session.commit()
    print(f"[floorplans] {created} sample floor plan(s) added.")


def main():
    app = create_app()
    with app.app_context():
        print("=== PHASE 3 MIGRATION - Smart Campus Navigation ===")
        backup_database()

        # Ensures the new campus_floor_plans table is created (existing tables untouched).
        db.create_all()
        add_is_panoramic_column()
        seed_phase3_nodes()
        seed_phase3_edges()
        seed_phase3_floor_plans()
        print("Phase 3 migration complete. All existing data preserved.")


if __name__ == "__main__":
    main()
