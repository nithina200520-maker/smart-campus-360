"""
Database migration script for Phase 2:
Adds is_verified, designation, semester, purpose_of_visit, reset_token, reset_token_expiry
to the users table without losing existing Phase 1 data.
Supports both MySQL and SQLite.
"""

from sqlalchemy import text, inspect
from app import create_app
from app.database import db

def run_migration():
    app = create_app()
    with app.app_context():
        print("Running Phase 2 database migration...")
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('users')]
        print(f"Existing columns in 'users': {columns}")

        new_columns = [
            ("is_verified", "BOOLEAN DEFAULT 1"),
            ("designation", "VARCHAR(100) NULL"),
            ("semester", "VARCHAR(20) NULL"),
            ("purpose_of_visit", "VARCHAR(150) NULL"),
            ("reset_token", "VARCHAR(100) NULL"),
            ("reset_token_expiry", "DATETIME NULL"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                print(f"Adding column '{col_name}' ({col_type})...")
                try:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
                    print(f"[OK] Added '{col_name}'.")
                except Exception as e:
                    db.session.rollback()
                    print(f"[!] Warning adding '{col_name}': {e}")
            else:
                print(f"[-] Column '{col_name}' already exists.")

        # Ensure seed teacher (Dr. Ramesh Kumar) has is_verified=True and designation set
        try:
            db.session.execute(text(
                "UPDATE users SET is_verified = 1, designation = 'Professor & Head' WHERE email = 'teacher@gechassan.ac.in'"
            ))
            db.session.execute(text(
                "UPDATE users SET semester = '5th Semester' WHERE email = 'student@gechassan.ac.in'"
            ))
            db.session.execute(text(
                "UPDATE users SET purpose_of_visit = 'Campus Enquiry' WHERE email = 'visitor@gechassan.ac.in'"
            ))
            db.session.commit()
            print("[OK] Seed users updated with Phase 2 verified metadata.")
        except Exception as e:
            db.session.rollback()
            print(f"[!] Note updating seed metadata: {e}")

        print("\nPhase 2 Migration completed successfully!")

if __name__ == '__main__':
    run_migration()
