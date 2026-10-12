"""
PHASE 4 TESTS - AI Lost & Found module.
Covers: multi-factor contextual ranking, image content validation, report-driven
matching + targeted in-app notifications, private match/contact access, the
claim -> admin-verification -> return workflow, admin controls and notification
history. Runs only against the throwaway test database (see conftest.py); the
real campus database is never touched.
"""
import io
from datetime import datetime, timedelta

import pytest

from tests.conftest import login, TEST_PASSWORD
from app.models import (
    LostFoundItem, LostFoundMatch, LostFoundClaim, Notification, AuditLog,
)
from app.utils.image_matcher import (
    rank_matches, context_factors, validate_image_bytes, load_embedding,
)


# --------------------------------------------------------------------------
# helpers / fixtures
# --------------------------------------------------------------------------
def _mk_item(db, owner, report_type, title, category="Electronics",
             colour="Black", location="Central Library", days_ago=0,
             description=None, status="open", vector=None):
    item = LostFoundItem(
        user_id=owner.id,
        report_type=report_type,
        title=title,
        category=category,
        location_reported=location,
        date_time_reported=datetime.utcnow() - timedelta(days=days_ago),
        description=description or f"{colour} {category.lower()} left at {location}",
        color_hint=colour,
        contact_phone="+91 98450 00000",
        status=status,
        image_feature_vector=vector,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture
def found_report(db, users):
    """A teacher reports a found black calculator in the library."""
    return _mk_item(db, users["teacher_verified"], "found",
                    title="Found Casio Calculator", category="Electronics",
                    colour="Black", location="Central Library")


# --------------------------------------------------------------------------
# 1. Contextual multi-factor ranking (category, colour, date, location)
# --------------------------------------------------------------------------
class TestContextualRanking:
    def test_identical_context_scores_high(self, db, users):
        a = _mk_item(db, users["student"], "lost", "Black Calculator",
                     category="Electronics", colour="Black", location="Central Library")
        b = _mk_item(db, users["teacher_verified"], "found", "Black Calculator",
                     category="Electronics", colour="Black", location="Central Library")
        f = context_factors(a, b)
        assert f["category"] == 1.0
        assert f["colour"] == 1.0
        assert f["location"] == 1.0
        assert f["blended"] >= 0.9

    def test_different_category_and_colour_scores_low(self, db, users):
        a = _mk_item(db, users["student"], "lost", "Red Water Bottle",
                     category="Personal Items", colour="Red", location="Canteen")
        b = _mk_item(db, users["teacher_verified"], "found", "Blue Calculator",
                     category="Electronics", colour="Blue", location="Library")
        f = context_factors(a, b)
        assert f["category"] == 0.0
        assert f["colour"] == 0.0
        assert f["blended"] < 0.3

    def test_rank_returns_only_above_threshold(self, db, users, found_report):
        lost = _mk_item(db, users["student"], "lost", "Found Calculator Match",
                        category="Electronics", colour="Black", location="Central Library")
        noise = _mk_item(db, users["visitor"], "found", "Unrelated Umbrella",
                         category="Other", colour="Red", location="Sports Ground",
                         description="red umbrella")
        candidates = LostFoundItem.query.filter_by(report_type="found").all()
        ranked = rank_matches(lost, candidates, min_composite=0.35, limit=10)
        ids = {r["item_id"] for r in ranked}
        assert found_report.id in ids
        assert noise.id not in ids

    def test_image_plus_context_when_embeddings_share_model(self, db, users):
        vec = '{"model": "hsv_histogram", "vector": [1.0, 0.5, 0.25]}'
        a = _mk_item(db, users["student"], "lost", "Item A", vector=vec)
        b = _mk_item(db, users["teacher_verified"], "found", "Item B", vector=vec)
        ranked = rank_matches(a, [b], min_composite=0.0, limit=5)
        assert ranked[0]["image_score"] == pytest.approx(1.0, abs=0.01)
        assert ranked[0]["composite_score"] >= 0.9


# --------------------------------------------------------------------------
# 2. Image content validation (SECURITY)
# --------------------------------------------------------------------------
class TestImageValidation:
    def test_rejects_non_image_bytes(self):
        assert validate_image_bytes(io.BytesIO(b"just plain text, not an image file")) is False

    def test_accepts_png_magic_bytes(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        assert validate_image_bytes(io.BytesIO(png)) is True

    def test_accepts_jpeg_magic_bytes(self):
        jpg = b"\xff\xd8\xff" + b"\x00" * 16
        assert validate_image_bytes(io.BytesIO(jpg)) is True

    def test_rejects_too_short(self):
        assert validate_image_bytes(io.BytesIO(b"\x89PNG")) is False

    def test_load_embedding_handles_legacy_and_dict(self):
        m, v = load_embedding("[0.1, 0.2, 0.3]")
        assert m == "hsv_histogram" and v == [0.1, 0.2, 0.3]
        m2, v2 = load_embedding('{"model": "mobilenetv2_imagenet", "vector": [1, 2]}')
        assert m2 == "mobilenetv2_imagenet" and v2 == [1, 2]


# --------------------------------------------------------------------------
# 3. Report -> match -> TARGETED notifications (never broadcast)
# --------------------------------------------------------------------------
class TestMatchingAndNotifications:
    def test_report_creates_match_and_notifies_only_involved_users(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        resp = client.post("/lost-found/report", data={
            "report_type": "lost",
            "title": "My Casio Calculator",
            "category": "Electronics",
            "location_reported": "Central Library",
            "description": "Black scientific calculator with yellow sticker",
            "color_hint": "Black",
            "contact_phone": "+91 98450 44004",
        }, follow_redirects=False)
        assert resp.status_code == 302

        assert LostFoundMatch.query.count() >= 1
        student_notes = Notification.query.filter_by(user_id=users["student"].id).count()
        teacher_notes = Notification.query.filter_by(user_id=users["teacher_verified"].id).count()
        assert student_notes >= 1 and teacher_notes >= 1
        # Unrelated accounts are never spammed
        assert Notification.query.filter_by(user_id=users["visitor"].id).count() == 0

    def test_match_list_hidden_from_non_owner(self, client, db, users, found_report):
        # Student owns a lost report that has a match; a different user must not see matches.
        lost = _mk_item(db, users["student"], "lost", "Lost Calculator",
                        category="Electronics", colour="Black", location="Central Library")
        LostFoundMatch.query.delete()
        db.session.commit()
        db.session.add(LostFoundMatch(lost_item_id=lost.id, found_item_id=found_report.id,
                                      similarity_score=0.9, composite_score=0.9, status="suggested"))
        db.session.commit()

        login(client, "teacher@gechassan.ac.in")  # a non-owner who is not this report's owner
        body = client.get(f"/lost-found/item/{lost.id}").get_data(as_text=True)
        assert "Match List Is Private" in body

    def test_owner_sees_matches_and_disclaimer(self, client, db, users, found_report):
        lost = _mk_item(db, users["student"], "lost", "Lost Calculator",
                        category="Electronics", colour="Black", location="Central Library")
        db.session.add(LostFoundMatch(lost_item_id=lost.id, found_item_id=found_report.id,
                                      similarity_score=0.9, composite_score=0.9,
                                      factors='{"category":1.0,"colour":1.0,"date_proximity":1.0,"location":1.0,"blended":1.0}',
                                      status="suggested"))
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        body = client.get(f"/lost-found/item/{lost.id}").get_data(as_text=True)
        assert "AI Similarity Matches" in body
        assert "not" in body and "proof of ownership" in body  # disclaimer present


# --------------------------------------------------------------------------
# 4. Claim -> verification -> return workflow
# --------------------------------------------------------------------------
class TestClaimWorkflow:
    def test_claim_requires_substantial_proof(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        resp = client.post(f"/lost-found/item/{found_report.id}/claim",
                           data={"proof_statement": "mine"}, follow_redirects=False)
        assert resp.status_code == 302
        assert LostFoundClaim.query.count() == 0
        db.session.refresh(found_report)
        assert found_report.status == "open"

    def test_cannot_claim_own_report(self, client, db, users):
        own = _mk_item(db, users["student"], "found", "My Own Found Item")
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{own.id}/claim",
                    data={"proof_statement": "I think this is mine actually"})
        assert LostFoundClaim.query.filter_by(item_id=own.id).count() == 0

    def test_valid_claim_creates_claim_and_notifies_reporter_and_admins(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{found_report.id}/claim",
                    data={"proof_statement": "The calculator has my USN 4GH22CS054 scratched on the back."},
                    follow_redirects=False)
        claim = LostFoundClaim.query.filter_by(item_id=found_report.id).first()
        assert claim is not None and claim.status == "pending"
        db.session.refresh(found_report)
        assert found_report.status == "claimed" and found_report.claimed_by_user_id == users["student"].id
        # reporter (teacher) + admins notified; unrelated visitor not
        assert Notification.query.filter_by(user_id=users["teacher_verified"].id).count() >= 1
        assert Notification.query.filter_by(user_id=users["main_admin"].id).count() >= 1
        assert Notification.query.filter_by(user_id=users["visitor"].id).count() == 0

    def test_duplicate_pending_claim_blocked(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        proof = {"proof_statement": "Distinctive yellow sticker and USN on the battery cover."}
        client.post(f"/lost-found/item/{found_report.id}/claim", data=proof)
        client.post(f"/lost-found/item/{found_report.id}/claim", data=proof)
        assert LostFoundClaim.query.filter_by(item_id=found_report.id, status="pending").count() == 1

    def test_admin_approve_then_record_return(self, client, db, users, found_report):
        # student files a claim
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{found_report.id}/claim",
                    data={"proof_statement": "USN 4GH22CS054 etched, yellow brand sticker on back."})
        claim = LostFoundClaim.query.filter_by(item_id=found_report.id).first()

        # admin approves
        client.get("/auth/logout")
        login(client, "admin@gechassan.ac.in")
        dresp = client.post(f"/admin/lost-found/claim/{claim.id}/decision",
                            data={"decision": "approve", "decision_note": "USN matched."})
        assert dresp.status_code == 302, dresp.get_data(as_text=True)[:400]
        db.session.refresh(claim)
        assert claim.status == "approved"

        # admin records the physical return
        client.post(f"/admin/lost-found/item/{found_report.id}/record-return",
                    data={"handover_note": "Collected with college ID at office."})
        db.session.refresh(found_report)
        assert found_report.status == "closed" and found_report.collected_at is not None

        # claimant is notified of approval + return
        assert Notification.query.filter_by(user_id=users["student"].id, category="claim").count() >= 1
        assert Notification.query.filter_by(user_id=users["student"].id, category="return").count() >= 1

    def test_admin_reject_reopens_item(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{found_report.id}/claim",
                    data={"proof_statement": "I believe the calculator is mine but cannot detail it."})
        claim = LostFoundClaim.query.filter_by(item_id=found_report.id).first()
        client.get("/auth/logout")
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/lost-found/claim/{claim.id}/decision",
                    data={"decision": "reject", "decision_note": "No unique identifiers given."})
        db.session.refresh(claim)
        db.session.refresh(found_report)
        assert claim.status == "rejected"
        assert found_report.status == "open" and found_report.claimed_by_user_id is None


# --------------------------------------------------------------------------
# 5. Main Admin controls
# --------------------------------------------------------------------------
class TestAdminControls:
    def test_student_cannot_access_lf_admin(self, client, users):
        login(client, "student@gechassan.ac.in")
        resp = client.get("/admin/lost-found", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_admin_page_and_stats_render(self, client, db, users, found_report):
        login(client, "admin@gechassan.ac.in")
        resp = client.get("/admin/lost-found")
        assert resp.status_code == 200
        assert "AI Lost" in resp.get_data(as_text=True)

    def test_admin_update_location_notifies_reporter(self, client, db, users, found_report):
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/lost-found/item/{found_report.id}/update-location",
                    data={"location_reported": "Lost & Found Office, Admin Block"})
        db.session.refresh(found_report)
        assert found_report.location_reported == "Lost & Found Office, Admin Block"
        assert Notification.query.filter_by(user_id=users["teacher_verified"].id, category="admin").count() >= 1

    def test_admin_verify_item_sets_verified(self, client, db, users, found_report):
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/lost-found/item/{found_report.id}/verify")
        db.session.refresh(found_report)
        assert found_report.verified_by_admin_id == users["main_admin"].id

    def test_admin_targeted_notification_only(self, client, db, users):
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/lost-found/notify/{users['student'].id}",
                    data={"title": "Please visit the office", "message": "Your item is ready for collection."})
        assert Notification.query.filter_by(user_id=users["student"].id).count() >= 1
        assert Notification.query.filter_by(user_id=users["visitor"].id).count() == 0


# --------------------------------------------------------------------------
# 6. Notification history, unread count, read state
# --------------------------------------------------------------------------
class TestNotificationHistory:
    def test_history_requires_login(self, client):
        resp = client.get("/notifications/", follow_redirects=False)
        assert resp.status_code == 302

    def test_unread_count_and_mark_read(self, client, db, users):
        Notification.notify(users["student"].id, title="T1", message="M1", category="match")
        Notification.notify(users["student"].id, title="T2", message="M2", category="claim")
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        body = client.get("/notifications/").get_data(as_text=True)
        assert "T1" in body and "T2" in body

        first = Notification.query.filter_by(user_id=users["student"].id).first()
        client.post(f"/notifications/mark-read/{first.id}")
        db.session.refresh(first)
        assert first.is_read is True

    def test_mark_all_read(self, client, db, users):
        for i in range(3):
            Notification.notify(users["student"].id, title=f"N{i}", message="x")
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        client.post("/notifications/mark-all-read")
        unread = Notification.query.filter_by(user_id=users["student"].id, is_read=False).count()
        assert unread == 0

    def test_cannot_mark_another_users_notification(self, client, db, users):
        note = Notification.notify(users["visitor"].id, title="V", message="x")
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        resp = client.post(f"/notifications/mark-read/{note.id}", follow_redirects=False)
        assert resp.status_code == 403
        db.session.refresh(note)
        assert note.is_read is False


# --------------------------------------------------------------------------
# 7. Personal dashboard + audit trail
# --------------------------------------------------------------------------
class TestPersonalDashboardAndAudit:
    def test_my_reports_lists_own_items_and_claims(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{found_report.id}/claim",
                    data={"proof_statement": "Yellow sticker and USN engraving confirm ownership."})
        body = client.get("/lost-found/my-reports").get_data(as_text=True)
        assert "Reports I Filed" in body
        assert "Found Casio Calculator" in body

    def test_claim_and_report_actions_are_audited(self, client, db, users, found_report):
        login(client, "student@gechassan.ac.in")
        client.post(f"/lost-found/item/{found_report.id}/claim",
                    data={"proof_statement": "USN engraving and brand sticker on the back cover."})
        assert AuditLog.query.filter_by(action="LF_CLAIM_SUBMITTED").count() >= 1
