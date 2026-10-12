"""Main Admin account lifecycle: canteen admin creation, activation,
verification, role changes — and audit logging of every action."""
from app.models import User, AuditLog
from tests.conftest import login


def test_admin_can_create_canteen_admin(client, users, db):
    login(client, "admin@gechassan.ac.in")
    resp = client.post("/admin/create-canteen-admin", data={
        "full_name": "New Canteen Operator", "email": "newops@gechassan.ac.in",
        "password": "OpsPass123", "department": "Campus Canteen",
    })
    assert resp.status_code == 302
    created = User.query.filter_by(email="newops@gechassan.ac.in").first()
    assert created is not None and created.role == "canteen_admin" and created.is_active
    assert AuditLog.query.filter_by(action="CANTEEN_ADMIN_CREATED").count() == 1


def test_canteen_admin_cannot_create_another_admin(client, users):
    login(client, "canteen@gechassan.ac.in")
    before = User.query.count()
    client.post("/admin/create-canteen-admin", data={
        "full_name": "Ghost", "email": "ghost@gechassan.ac.in", "password": "GhostPass1",
    })
    assert User.query.count() == before


def test_admin_can_deactivate_and_reactivate_account(client, users, db):
    login(client, "admin@gechassan.ac.in")
    client.post(f"/admin/users/{users['student'].id}/toggle-status")
    assert users["student"].is_active is False
    assert AuditLog.query.filter_by(action="USER_DEACTIVATED").count() == 1
    client.post(f"/admin/users/{users['student'].id}/toggle-status")
    assert users["student"].is_active is True
    assert AuditLog.query.filter_by(action="USER_ACTIVATED").count() == 1


def test_main_admin_account_cannot_be_suspended(client, users, db):
    login(client, "admin@gechassan.ac.in")
    client.post(f"/admin/users/{users['main_admin'].id}/toggle-status")
    assert users["main_admin"].is_active is True


def test_verify_and_revoke_teacher_flow(client, users, db):
    login(client, "admin@gechassan.ac.in")
    client.post(f"/admin/users/{users['teacher_pending'].id}/verify-teacher")
    assert users["teacher_pending"].is_verified is True
    assert AuditLog.query.filter_by(action="TEACHER_VERIFIED").count() == 1
    client.post(f"/admin/users/{users['teacher_pending'].id}/revoke-teacher")
    assert users["teacher_pending"].is_verified is False
    assert AuditLog.query.filter_by(action="TEACHER_VERIFICATION_REVOKED").count() == 1


def test_role_change_to_teacher_resets_verification(client, users, db):
    login(client, "admin@gechassan.ac.in")
    client.post(f"/admin/users/{users['student'].id}/change-role", data={"new_role": "teacher"})
    assert users["student"].role == "teacher"
    assert users["student"].is_verified is False  # must be re-verified
    assert AuditLog.query.filter_by(action="USER_ROLE_CHANGED").count() == 1


def test_admin_audit_log_viewer(client, users):
    login(client, "admin@gechassan.ac.in")
    resp = client.get("/admin/audit-logs")
    assert resp.status_code == 200
    assert "USER_LOGIN_SUCCESS" in resp.get_data(as_text=True)
