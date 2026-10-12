"""Password reset procedures: token lifecycle, expiry, and unknown emails."""
from datetime import datetime, timedelta

from app.models import User, AuditLog
from tests.conftest import login


def test_forgot_password_page_loads(client):
    assert client.get("/auth/forgot-password").status_code == 200


def test_reset_token_issued_for_valid_active_email(client, users):
    resp = client.post("/auth/forgot-password", data={"email": "student@gechassan.ac.in"})
    body = resp.get_data(as_text=True)
    user = users["student"]
    assert user.reset_token and user.reset_token_expiry > datetime.utcnow()
    assert "/auth/reset-password/" in body
    assert AuditLog.query.filter_by(action="PASSWORD_RESET_TOKEN_GENERATED").count() == 1


def test_unknown_email_gets_generic_response(client, users):
    resp = client.post("/auth/forgot-password", data={"email": "ghost@nowhere.com"})
    body = resp.get_data(as_text=True)
    assert "If that email address exists" in body  # no user enumeration
    assert "/auth/reset-password/" not in body


def test_deactivated_user_cannot_reset(client, users):
    client.post("/auth/forgot-password", data={"email": "inactive@gechassan.ac.in"})
    assert users["inactive"].reset_token is None


def test_full_reset_flow_changes_password(client, users):
    client.post("/auth/forgot-password", data={"email": "student@gechassan.ac.in"})
    token = users["student"].reset_token
    resp = client.post(f"/auth/reset-password/{token}", data={
        "password": "BrandNew1Pass", "confirm_password": "BrandNew1Pass",
    })
    assert resp.status_code == 302
    client.get("/auth/logout")
    assert login(client, "student@gechassan.ac.in", "Testpass123").status_code == 200  # old password dead
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert login(client, "student@gechassan.ac.in", "BrandNew1Pass").status_code == 302
    assert users["student"].reset_token is None  # token cleared after use
    assert AuditLog.query.filter_by(action="PASSWORD_RESET_COMPLETED").count() == 1


def test_invalid_token_rejected(client, users):
    resp = client.get("/auth/reset-password/not-a-real-token-xyz")
    assert resp.status_code == 302  # bounced back to forgot-password


def test_expired_token_rejected(client, users, db):
    client.post("/auth/forgot-password", data={"email": "student@gechassan.ac.in"})
    expired_token = users["student"].reset_token
    users["student"].reset_token_expiry = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    resp = client.get(f"/auth/reset-password/{expired_token}")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/forgot-password")
    # Password must be untouched
    assert login(client, "student@gechassan.ac.in").status_code == 302


def test_weak_password_rejected_on_reset(client, users):
    client.post("/auth/forgot-password", data={"email": "student@gechassan.ac.in"})
    token = users["student"].reset_token
    resp = client.post(f"/auth/reset-password/{token}", data={
        "password": "short", "confirm_password": "short",
    })
    assert resp.status_code == 200  # re-rendered with warning
    assert User.query.filter_by(email="student@gechassan.ac.in").first().reset_token == token
