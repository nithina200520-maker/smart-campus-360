"""Authentication: login/logout, registration rules, hashing, activation."""
from app.models import User, AuditLog
from tests.conftest import login, TEST_PASSWORD


def test_login_page_loads(client):
    assert client.get("/auth/login").status_code == 200


def test_valid_login_sets_session_and_redirects(client, users):
    resp = login(client, "student@gechassan.ac.in")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_role"] == "student"


def test_admin_and_canteen_admin_land_on_own_dashboards(client, users):
    assert login(client, "admin@gechassan.ac.in").headers["Location"].endswith("/admin/dashboard")
    client.get("/auth/logout")
    assert login(client, "canteen@gechassan.ac.in").headers["Location"].endswith("/canteen-admin/dashboard")


def test_invalid_password_rejected(client, users):
    resp = client.post("/auth/login", data={"email": "student@gechassan.ac.in", "password": "WrongPass9"})
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert resp.status_code == 200  # re-renders login page


def test_deactivated_account_cannot_login(client, users):
    login_resp = login(client, "inactive@gechassan.ac.in")
    assert login_resp.status_code == 200  # blocked, no session
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert AuditLog.query.filter_by(action="LOGIN_BLOCKED_INACTIVE").count() == 1


def test_logout_clears_session(client, users):
    login(client, "student@gechassan.ac.in")
    client.get("/auth/logout")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_login_and_logout_are_audit_logged(client, users):
    login(client, "student@gechassan.ac.in")
    client.get("/auth/logout")
    assert AuditLog.query.filter_by(action="USER_LOGIN_SUCCESS").count() == 1
    assert AuditLog.query.filter_by(action="USER_LOGOUT").count() == 1


def test_passwords_are_hashed_never_plaintext(client, db):
    client.post("/auth/register", data={
        "full_name": "Hash Check", "email": "hash@gechassan.ac.in",
        "password": "Str0ngPass99", "confirm_password": "Str0ngPass99",
        "role": "student", "usn": "4GH22CS999",
    })
    user = User.query.filter_by(email="hash@gechassan.ac.in").first()
    assert user and user.password_hash != "Str0ngPass99"
    assert user.password_hash.startswith(("pbkdf2:", "scrypt:"))


def test_student_registration_creates_active_verified_account(client, db):
    resp = client.post("/auth/register", data={
        "full_name": "New Student", "email": "new.student@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD,
        "role": "student", "usn": "4GH22CS100", "semester": "3rd Semester",
    }, follow_redirects=True)
    user = User.query.filter_by(email="new.student@gechassan.ac.in").first()
    assert user is not None and user.role == "student" and user.is_active
    assert "Registration successful" in resp.get_data(as_text=True)


def test_teacher_registration_starts_unverified_pending(client, db):
    client.post("/auth/register", data={
        "full_name": "Pending Faculty", "email": "fresh.teacher@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD,
        "role": "teacher", "employee_id": "EMP-CSE-777", "designation": "Assistant Professor",
    })
    user = User.query.filter_by(email="fresh.teacher@gechassan.ac.in").first()
    assert user is not None and user.is_verified is False
    assert AuditLog.query.filter_by(action="TEACHER_REGISTERED_PENDING_VERIFICATION").count() == 1


def test_visitor_registration_allowed(client, db):
    client.post("/auth/register", data={
        "full_name": "Guest User", "email": "guest@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD,
        "role": "visitor", "purpose_of_visit": "Parent Meeting",
    })
    assert User.query.filter_by(email="guest@gechassan.ac.in", role="visitor").first() is not None


def test_public_registration_cannot_create_main_admin(client, db):
    client.post("/auth/register", data={
        "full_name": "Evil Admin", "email": "evil@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD,
        "role": "main_admin",
    })
    assert User.query.filter_by(email="evil@gechassan.ac.in").first() is None
    assert AuditLog.query.filter_by(action="UNAUTHORIZED_ADMIN_REGISTRATION_ATTEMPT").count() == 1


def test_public_registration_cannot_create_canteen_admin(client, db):
    client.post("/auth/register", data={
        "full_name": "Evil Canteen", "email": "evil2@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD,
        "role": "canteen_admin",
    })
    assert User.query.filter_by(email="evil2@gechassan.ac.in").first() is None


def test_weak_password_rejected(client, db):
    client.post("/auth/register", data={
        "full_name": "Weak", "email": "weak@gechassan.ac.in",
        "password": "abc", "confirm_password": "abc", "role": "student",
    })
    assert User.query.filter_by(email="weak@gechassan.ac.in").first() is None


def test_duplicate_email_rejected(client, users):
    before = User.query.count()
    client.post("/auth/register", data={
        "full_name": "Dup", "email": "student@gechassan.ac.in",
        "password": TEST_PASSWORD, "confirm_password": TEST_PASSWORD, "role": "student",
    })
    assert User.query.count() == before
