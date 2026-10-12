"""
SMART CAMPUS 360 - Phase 2 Test Suite (conftest)
Isolated pytest fixtures: the whole suite runs against a throwaway SQLite file
in the system temp directory. The real Phase 1 database
(instance/smart_campus_360.db) is NEVER opened by tests.
"""
import os
import tempfile

# CRITICAL: env must be set BEFORE `app.config` is imported (its URI is
# computed once at class-definition time; Flask-SQLAlchemy binds engines
# inside create_app, so overriding app config afterwards is too late).
_TEST_DB_DIR = tempfile.mkdtemp(prefix="sc360_testdb_")
os.environ["USE_SQLITE"] = "True"
os.environ["SQLITE_DB_PATH"] = os.path.join(_TEST_DB_DIR, "test_sc360.db")

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.database import db as _db
from app.models import User

# Shared password for seeded test accounts (test DB only, never production)
TEST_PASSWORD = "Testpass123"


def fast_hash(password: str) -> str:
    """Low-iteration PBKDF2 so the suite stays fast; check_password_hash auto-detects."""
    return generate_password_hash(password, method="pbkdf2:sha256:1000")


@pytest.fixture
def app(tmp_path):
    # Engine is bound to the throwaway DB via SQLITE_DB_PATH env (set above)
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(db, role, email, full_name, is_verified=True, is_active=True, **extra):
    user = User(
        full_name=full_name,
        email=email,
        role=role,
        is_verified=is_verified,
        is_active=is_active,
        **extra,
    )
    user.password_hash = fast_hash(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def users(db):
    """One seeded account per institutional role (mirrors init_db.py personas)."""
    return {
        "main_admin": _make_user(db, "main_admin", "admin@gechassan.ac.in", "College System Administrator", department="System Administration"),
        "canteen_admin": _make_user(db, "canteen_admin", "canteen@gechassan.ac.in", "Canteen Supervisor"),
        "teacher_verified": _make_user(db, "teacher", "teacher@gechassan.ac.in", "Dr. Ramesh Kumar", designation="Professor & Head", usn_or_emp_id="EMP-CSE-042"),
        "teacher_pending": _make_user(db, "teacher", "pending.teacher@gechassan.ac.in", "New Faculty Member", is_verified=False, designation="Assistant Professor", usn_or_emp_id="EMP-ECE-101"),
        "student": _make_user(db, "student", "student@gechassan.ac.in", "Sneha Patil", usn_or_emp_id="4GH22CS054", semester="5th Semester"),
        "visitor": _make_user(db, "visitor", "visitor@gechassan.ac.in", "Anand Sharma", purpose_of_visit="Campus Enquiry"),
        "inactive": _make_user(db, "student", "inactive@gechassan.ac.in", "Suspended Student", is_active=False),
    }


def login(client, email, password=TEST_PASSWORD):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
