"""Visitor accounts: public navigation allowed, private user data restricted."""
from datetime import datetime

from app.models import LostFoundItem
from tests.conftest import login


def _seed_report(db, users):
    item = LostFoundItem(
        user_id=users["student"].id,
        report_type="lost",
        title="Lost Wallet",
        category="Personal Items",
        location_reported="Canteen",
        date_time_reported=datetime.utcnow(),
        description="Brown leather wallet",
        contact_phone="+91 98450 44004",
        status="open",
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_visitor_can_use_public_navigation(client, users):
    login(client, "visitor@gechassan.ac.in")
    assert client.get("/navigation/").status_code == 200
    assert client.get("/lost-found/").status_code == 200


def test_visitor_cannot_see_private_contact_data(client, users, db):
    item = _seed_report(db, users)
    login(client, "visitor@gechassan.ac.in")
    body = client.get(f"/lost-found/item/{item.id}").get_data(as_text=True)
    assert "+91 98450 44004" not in body
    assert "Sneha Patil" not in body
    assert "Restricted (Visitor Access)" in body


def test_student_can_still_see_report_details(client, users, db):
    item = _seed_report(db, users)
    login(client, "student@gechassan.ac.in")
    body = client.get(f"/lost-found/item/{item.id}").get_data(as_text=True)
    assert "+91 98450 44004" in body


def test_visitor_owns_report_sees_own_data(client, users, db):
    item = LostFoundItem(
        user_id=users["visitor"].id, report_type="found", title="Found Umbrella",
        category="Other", location_reported="Library",
        date_time_reported=datetime.utcnow(), description="Black umbrella",
        contact_phone="+91 98450 55005", status="open",
    )
    db.session.add(item)
    db.session.commit()
    login(client, "visitor@gechassan.ac.in")
    body = client.get(f"/lost-found/item/{item.id}").get_data(as_text=True)
    assert "+91 98450 55005" in body


def test_visitor_cannot_file_ownership_claims(client, users, db):
    item = _seed_report(db, users)
    login(client, "visitor@gechassan.ac.in")
    resp = client.post(f"/lost-found/item/{item.id}/claim")
    assert resp.status_code == 302  # redirected away by restrict_visitors
    db.session.refresh(item)
    assert item.claimed_by_user_id is None and item.status == "open"


def test_verified_teacher_can_file_claim(client, users, db):
    item = _seed_report(db, users)
    login(client, "teacher@gechassan.ac.in")
    client.post(f"/lost-found/item/{item.id}/claim")
    db.session.refresh(item)
    assert item.claimed_by_user_id == users["teacher_verified"].id
