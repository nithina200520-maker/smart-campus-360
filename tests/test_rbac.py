"""Role-based authorization: route protection matrix + quick-switch lockdown."""
from app.models import AuditLog
from tests.conftest import login


def _is_blocked(resp):
    """role_required denial redirects to the landing portal."""
    return resp.status_code == 302 and resp.headers["Location"].endswith("/")


def test_anonymous_redirected_to_login_for_protected_pages(client):
    for path in ("/admin/dashboard", "/canteen-admin/dashboard", "/auth/profile", "/canteen/my-orders"):
        resp = client.get(path)
        assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"], path


def test_public_pages_available_without_login(client):
    for path in ("/", "/navigation/", "/lost-found/", "/canteen/"):
        assert client.get(path).status_code == 200, path


def test_student_denied_admin_dashboard(client, users):
    login(client, "student@gechassan.ac.in")
    assert _is_blocked(client.get("/admin/dashboard"))
    assert AuditLog.query.filter_by(action="ACCESS_DENIED_ROLE", user_id=users["student"].id).count() == 1


def test_canteen_admin_denied_main_admin_area(client, users):
    login(client, "canteen@gechassan.ac.in")
    assert _is_blocked(client.get("/admin/dashboard"))
    assert _is_blocked(client.get("/admin/users"))


def test_canteen_admin_limited_to_canteen_management_only(client, users):
    login(client, "canteen@gechassan.ac.in")
    assert client.get("/canteen-admin/dashboard").status_code == 200
    # Canteen Admin must NOT reach main-admin user management or audit logs
    assert _is_blocked(client.get("/admin/create-canteen-admin"))
    assert _is_blocked(client.get("/admin/audit-logs"))


def test_main_admin_has_universal_clearance(client, users):
    login(client, "admin@gechassan.ac.in")
    assert client.get("/admin/dashboard").status_code == 200
    assert client.get("/canteen-admin/dashboard").status_code == 200  # master access


def test_teacher_student_visitor_denied_canteen_admin(client, users):
    for email in ("teacher@gechassan.ac.in", "student@gechassan.ac.in", "visitor@gechassan.ac.in"):
        client.get("/auth/logout")
        login(client, email)
        assert _is_blocked(client.get("/canteen-admin/dashboard")), email


def test_deactivated_user_session_invalidated_immediately(client, users, db):
    login(client, "student@gechassan.ac.in")
    assert client.get("/auth/profile").status_code == 200
    users["student"].is_active = False
    db.session.commit()
    resp = client.get("/auth/profile")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_quick_switch_forbidden_outside_development(client, users):
    # Testing/production config: privilege-escalation endpoint must be 403
    resp = client.get("/auth/quick-switch/main_admin")
    assert resp.status_code == 403
    assert AuditLog.query.filter_by(action="QUICK_SWITCH_BLOCKED_PRODUCTION").count() == 1
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_quick_switch_available_in_development_mode(client, users, app):
    app.config["ALLOW_QUICK_SWITCH"] = True
    resp = client.get("/auth/quick-switch/main_admin")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_role"] == "main_admin"


def test_role_switch_pill_hidden_in_production(client, users, app):
    app.config["ALLOW_QUICK_SWITCH"] = False
    body = client.get("/").get_data(as_text=True)
    assert "Switch Role" not in body
    app.config["ALLOW_QUICK_SWITCH"] = True
    body = client.get("/").get_data(as_text=True)
    assert "Switch Role" in body
