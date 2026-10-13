"""
PHASE 5 TESTS - Improved Lost & Found AI and Notifications.
Covers: preprocessing + embedding payloads, metadata (text) similarity and
confidence bands, duplicate-report detection, notification dedup, match-pair
idempotency, Main Admin match confirm/reject review, the AI testing lab and
the evaluation harness. Runs only against the throwaway test database
(see conftest.py); the real campus database is never touched.
"""
import io
import json
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

from tests.conftest import login
from app.models import (
    LostFoundItem, LostFoundMatch, Notification, AuditLog,
)
from app.utils.image_matcher import (
    extract_image_features, load_embedding, compute_cosine_similarity,
    context_factors, text_similarity, confidence_band, rank_matches,
    find_duplicate_report, duplicate_score, analyze_image_against_registry,
    QueryItem, _preprocess_image, CNN_MODEL, HISTOGRAM_MODEL,
)


# --------------------------------------------------------------------------
# helpers
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


def _png_bytes(seed=1):
    rng = np.random.default_rng(seed)
    canvas = np.full((180, 180, 3), 240, np.uint8)
    cv2.rectangle(canvas, (30, 50), (150, 130), (40, 40, 180), -1)
    canvas = cv2.add(canvas, rng.integers(0, 8, canvas.shape, dtype=np.uint8))
    ok, buf = cv2.imencode('.png', canvas)
    assert ok
    return buf.tobytes()


def _report_form(title="Lost Black Wallet", category="Personal Items",
                 colour="Black", location="Canteen Area",
                 description="Black leather wallet with college ID card inside"):
    return {
        "report_type": "lost", "title": title, "category": category,
        "location_reported": location, "description": description,
        "color_hint": colour, "contact_phone": "+91 98450 11111",
    }


# --------------------------------------------------------------------------
# 1. Preprocessing + embedding generation
# --------------------------------------------------------------------------
class TestPreprocessingAndEmbeddings:
    def test_preprocess_reports_all_stages(self):
        img = np.full((300, 300, 3), 235, np.uint8)
        cv2.rectangle(img, (90, 110), (210, 190), (30, 30, 160), -1)
        prepared, info = _preprocess_image(img)
        assert set(info) == {"cropped", "white_balance", "clahe"}
        assert info["clahe"] is True
        assert prepared.ndim == 3 and prepared.shape[0] >= 32

    def test_extract_returns_versioned_normalized_payload(self, tmp_path):
        p = tmp_path / "item.png"
        p.write_bytes(_png_bytes())
        data = json.loads(extract_image_features(str(p)))
        assert data["model"] in (CNN_MODEL, HISTOGRAM_MODEL)
        assert data["pre"] == "sc360-ph5-crop-wb-clahe"
        assert len(data["vector"]) > 0
        assert abs(np.linalg.norm(np.array(data["vector"])) - 1.0) < 1e-3

    def test_identical_images_are_maximally_similar(self, tmp_path):
        a, b = tmp_path / "a.png", tmp_path / "b.png"
        blob = _png_bytes(7)
        a.write_bytes(blob)
        b.write_bytes(blob)
        va, vb = extract_image_features(str(a)), extract_image_features(str(b))
        m1, x1 = load_embedding(va)
        m2, x2 = load_embedding(vb)
        assert m1 == m2
        assert compute_cosine_similarity(x1, x2) == pytest.approx(1.0, abs=1e-3)

    def test_missing_file_returns_none(self):
        assert extract_image_features("Z:/definitely/not/here.png") is None

    def test_legacy_bare_vectors_still_load(self):
        model, vec = load_embedding("[0.2, 0.4]")
        assert model == HISTOGRAM_MODEL and vec == [0.2, 0.4]


# --------------------------------------------------------------------------
# 2. Metadata matching + similarity ranking improvements
# --------------------------------------------------------------------------
class TestMetadataAndRanking:
    def test_factors_include_text_signal(self, db, users):
        a = _mk_item(db, users["student"], "lost", "Black Calculator Casio",
                     description="black casio scientific calculator")
        b = _mk_item(db, users["teacher_verified"], "found", "Black Calculator Casio",
                     description="black casio scientific calculator")
        f = context_factors(a, b)
        assert f["text"] == pytest.approx(1.0)
        assert f["blended"] >= 0.9

    def test_text_similarity_partial_overlap(self, db, users):
        a = _mk_item(db, users["student"], "lost", "Black Wallet Leather",
                     description="black leather wallet", category="Personal Items")
        b = _mk_item(db, users["teacher_verified"], "found", "Black Backpack",
                     description="black college backpack", category="Personal Items")
        assert 0.0 < text_similarity(a, b) < 1.0

    def test_confidence_bands_use_thresholds(self):
        assert confidence_band(0.80, strong=0.70, medium=0.50) == "high"
        assert confidence_band(0.60, strong=0.70, medium=0.50) == "medium"
        assert confidence_band(0.40, strong=0.70, medium=0.50) == "possible"

    def test_rank_result_carries_band_days_and_model(self, db, users):
        a = _mk_item(db, users["student"], "lost", "Black Calculator")
        b = _mk_item(db, users["teacher_verified"], "found", "Black Calculator")
        ranked = rank_matches(a, [b], min_composite=0.35, limit=5)
        assert len(ranked) == 1
        r = ranked[0]
        assert r["confidence_band"] in ("high", "medium", "possible")
        assert r["days_apart"] == 0.0
        assert r["text_score"] >= 0.0
        assert r["embedding_model"] == "none"  # no photos stored

    def test_deterministic_tie_break_prefers_closer_date(self, db, users):
        q = _mk_item(db, users["student"], "lost", "Black Calculator")
        near = _mk_item(db, users["teacher_verified"], "found", "Black Calculator", days_ago=2)
        far = _mk_item(db, users["visitor"], "found", "Black Calculator", days_ago=30)
        ranked = rank_matches(q, [far, near], min_composite=0.0, limit=5)
        assert ranked[0]["item_id"] == near.id


# --------------------------------------------------------------------------
# 3. Duplicate report detection
# --------------------------------------------------------------------------
class TestDuplicateReportDetection:
    def test_helper_flags_same_user_repeat_report(self, db, users):
        first = _mk_item(db, users["student"], "lost", "Black Wallet Leather",
                         category="Personal Items", colour="Black",
                         location="Canteen Area",
                         description="black leather wallet with id card")
        second = _mk_item(db, users["student"], "lost", "Black Wallet Leather",
                          category="Personal Items", colour="Black",
                          location="Canteen Area",
                          description="black leather wallet with id card")
        dup = find_duplicate_report(second, [first, second])
        assert dup is not None and dup["item_id"] == first.id
        assert dup["score"] >= 0.65

    def test_different_users_are_not_duplicates(self, db, users):
        mine = _mk_item(db, users["student"], "lost", "Black Water Bottle",
                        category="Personal Items",
                        description="black bottle")
        theirs = _mk_item(db, users["teacher_verified"], "lost", "Black Water Bottle",
                          category="Personal Items",
                          description="black bottle")
        assert find_duplicate_report(theirs, [mine, theirs]) is None

    def test_different_items_are_not_duplicates(self, db, users):
        wallet = _mk_item(db, users["student"], "lost", "Black Wallet Leather",
                          category="Personal Items", description="black leather wallet")
        keys = _mk_item(db, users["student"], "lost", "Brass Key Ring",
                        category="Valuables", colour="Silver",
                        description="keys with red lanyard", location="Lab Block")
        assert find_duplicate_report(keys, [wallet, keys]) is None

    def test_duplicate_score_components(self, db, users):
        a = _mk_item(db, users["student"], "found", "Red Umbrella",
                     category="Other", colour="Red", description="red umbrella")
        b = _mk_item(db, users["student"], "found", "Red Umbrella",
                     category="Other", colour="Red", description="red umbrella")
        s = duplicate_score(a, b)
        assert s["text"] == 1.0 and s["colour"] == 1.0 and s["score"] >= 0.65

    def test_report_route_flags_duplicate_and_skips_alerts(self, client, db, users):
        login(client, "student@gechassan.ac.in")
        client.post("/lost-found/report", data=_report_form(), follow_redirects=False)
        notes_before = Notification.query.count()
        resp = client.post("/lost-found/report", data=_report_form(), follow_redirects=False)
        assert resp.status_code == 302
        dup = LostFoundItem.query.order_by(LostFoundItem.id.desc()).first()
        assert dup.is_duplicate is True
        assert dup.duplicate_of_id == LostFoundItem.query.order_by(LostFoundItem.id.asc()).first().id
        # no duplicate match alerts generated for the duplicate report
        assert Notification.query.count() == notes_before
        assert LostFoundMatch.query.count() == 0
        assert AuditLog.query.filter_by(action="LF_DUPLICATE_REPORT_FLAGGED").count() == 1


# --------------------------------------------------------------------------
# 4. Notification dedup (no duplicate alerts for the same match)
# --------------------------------------------------------------------------
class TestNotificationDedup:
    def test_same_dedup_key_notifies_once(self, db, users):
        uid = users["student"].id
        first = Notification.notify(uid, title="T", message="M", category="match",
                                    dedup_key="lf-match:pair:1-2:u1")
        db.session.commit()
        again = Notification.notify(uid, title="T", message="M", category="match",
                                    dedup_key="lf-match:pair:1-2:u1")
        db.session.commit()
        assert first is not None and again is None
        assert Notification.query.filter_by(dedup_key="lf-match:pair:1-2:u1").count() == 1

    def test_distinct_keys_and_legacy_null_keys_allowed(self, db, users):
        uid = users["student"].id
        Notification.notify(uid, title="A", message="x", dedup_key="k-a")
        Notification.notify(uid, title="B", message="x", dedup_key="k-b")
        Notification.notify(uid, title="C", message="x")  # no key (legacy path)
        Notification.notify(uid, title="D", message="x")  # no key again
        db.session.commit()
        assert Notification.query.filter_by(user_id=uid).count() == 4

    def test_repeat_submission_does_not_duplicate_pair_or_alerts(self, client, db, users):
        """An identical resubmission is caught by duplicate detection, so the
        stored (lost, found) pair row and its alerts can never double up."""
        found = _mk_item(db, users["teacher_verified"], "found", "Black Calculator")
        lost = _mk_item(db, users["student"], "lost", "Black Calculator")
        db.session.add(LostFoundMatch(lost_item_id=lost.id, found_item_id=found.id,
                                      similarity_score=0.9, composite_score=0.9,
                                      status="suggested"))
        db.session.commit()
        notes_before = Notification.query.count()
        login(client, "student@gechassan.ac.in")
        client.post("/lost-found/report", data={
            "report_type": "lost", "title": "Black Calculator",
            "category": "Electronics", "location_reported": "Central Library",
            "description": "black electronics left at central library",
            "color_hint": "Black", "contact_phone": "+91 98450 11111"},
            follow_redirects=False)
        assert LostFoundMatch.query.filter_by(lost_item_id=lost.id,
                                              found_item_id=found.id).count() == 1
        assert LostFoundMatch.query.count() == 1
        assert Notification.query.count() == notes_before


# --------------------------------------------------------------------------
# 5. Main Admin match review: confirm / reject
# --------------------------------------------------------------------------
class TestAdminMatchReview:
    def _pair_with_suggestion(self, db, users):
        lost = _mk_item(db, users["student"], "lost", "Black Calculator")
        found = _mk_item(db, users["teacher_verified"], "found", "Black Calculator")
        match = LostFoundMatch(lost_item_id=lost.id, found_item_id=found.id,
                               similarity_score=0.88, composite_score=0.91,
                               factors='{"category":1.0,"colour":1.0,"date_proximity":1.0,'
                                       '"location":1.0,"text":1.0,"blended":1.0}',
                               status="suggested")
        db.session.add(match)
        db.session.commit()
        return lost, found, match

    def test_review_queue_visible_on_admin_page(self, client, db, users):
        self._pair_with_suggestion(db, users)
        login(client, "admin@gechassan.ac.in")
        body = client.get("/admin/lost-found").get_data(as_text=True)
        assert "Suggested AI Matches Awaiting Your Review" in body

    def test_admin_confirm_verifies_and_notifies_once(self, client, db, users):
        lost, found, match = self._pair_with_suggestion(db, users)
        login(client, "admin@gechassan.ac.in")
        resp = client.post(f"/admin/lost-found/match/{match.id}/decision",
                           data={"decision": "confirm"}, follow_redirects=False)
        assert resp.status_code == 302
        db.session.refresh(match)
        assert match.status == "verified"
        assert match.decided_by_admin_id == users["main_admin"].id
        assert match.decided_at is not None
        db.session.refresh(lost)
        db.session.refresh(found)
        assert lost.status == "matched" and found.status == "matched"
        # both involved users notified exactly once (second POST cannot re-alert)
        assert Notification.query.filter_by(user_id=lost.user_id, category="match").count() == 1
        assert Notification.query.filter_by(user_id=found.user_id, category="match").count() == 1
        client.post(f"/admin/lost-found/match/{match.id}/decision",
                    data={"decision": "confirm"})
        assert Notification.query.filter_by(category="match").count() == 2
        assert AuditLog.query.filter_by(action="LF_MATCH_CONFIRMED").count() == 1

    def test_admin_reject_records_reason(self, client, db, users):
        lost, found, match = self._pair_with_suggestion(db, users)
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/lost-found/match/{match.id}/decision",
                    data={"decision": "reject", "reason": "Different brand and colour."})
        db.session.refresh(match)
        assert match.status == "rejected"
        assert match.rejected_reason == "Different brand and colour."
        assert AuditLog.query.filter_by(action="LF_MATCH_REJECTED").count() == 1

    def test_non_admin_cannot_decide_matches(self, client, db, users):
        _, _, match = self._pair_with_suggestion(db, users)
        login(client, "student@gechassan.ac.in")
        resp = client.post(f"/admin/lost-found/match/{match.id}/decision",
                           data={"decision": "confirm"}, follow_redirects=False)
        assert resp.status_code in (302, 403)
        db.session.refresh(match)
        assert match.status == "suggested"

    def test_owner_detail_shows_decision_badge(self, client, db, users):
        lost, found, match = self._pair_with_suggestion(db, users)
        match.status = "rejected"
        match.rejected_reason = "Not the same device."
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        body = client.get(f"/lost-found/item/{lost.id}").get_data(as_text=True)
        assert "Admin rejected this pairing" in body
        assert "Not the same device." in body


# --------------------------------------------------------------------------
# 6. AI testing lab (images, scores, ranks, errors)
# --------------------------------------------------------------------------
class TestAILab:
    def test_lab_requires_main_admin(self, client, users):
        login(client, "student@gechassan.ac.in")
        resp = client.get("/admin/ai-lab", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_lab_page_renders_for_admin(self, client, users):
        login(client, "admin@gechassan.ac.in")
        resp = client.get("/admin/ai-lab")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "AI Match Lab" in body
        assert "Embedding" in body or "embedding" in body

    def test_lab_analysis_shows_image_and_scores(self, client, db, users):
        _mk_item(db, users["teacher_verified"], "found", "Black Calculator",
                 category="Electronics", colour="Black", location="Central Library")
        login(client, "admin@gechassan.ac.in")
        data = {
            "photo": (io.BytesIO(_png_bytes(3)), "test.png"),
            "title": "Black Calculator", "category": "Electronics",
            "color_hint": "Black", "location_reported": "Central Library",
            "description": "black electronics left at central library",
            "compare_type": "found", "min_composite": "0.2", "limit": "10",
        }
        resp = client.post("/admin/ai-lab", data=data,
                           content_type="multipart/form-data")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Uploaded Test Image" in body          # image echoed back
        assert "Embedding Diagnostics" in body        # model + dims + preprocessing
        assert "Ranked Similarity Matches" in body
        assert "data:image;base64" in body

    def test_lab_rejects_non_image_file_with_error(self, client, users):
        login(client, "admin@gechassan.ac.in")
        data = {"photo": (io.BytesIO(b"definitely not image bytes!!"), "fake.png"),
                "title": "x", "category": "Other", "compare_type": "found"}
        body = client.post("/admin/ai-lab", data=data,
                           content_type="multipart/form-data").get_data(as_text=True)
        assert "Rejected: not a valid" in body

    def test_lab_requires_a_photograph(self, client, users):
        login(client, "admin@gechassan.ac.in")
        body = client.post("/admin/ai-lab", data={"title": "no photo"},
                           content_type="multipart/form-data").get_data(as_text=True)
        assert "Attach a photograph" in body

    def test_analyze_helper_reports_model_and_errors(self, tmp_path, db, users):
        p = tmp_path / "q.png"
        p.write_bytes(_png_bytes(11))
        candidate = _mk_item(db, users["teacher_verified"], "found", "Blue Water Bottle",
                             category="Personal Items", colour="Blue",
                             location="Canteen")
        out = analyze_image_against_registry(
            str(p), {"title": "Blue Bottle", "category": "Personal Items",
                     "color_hint": "Blue", "location_reported": "Canteen",
                     "description": "blue bottle"}, [candidate],
            min_composite=0.0, limit=5)
        assert out["ok"] is True and out["error"] is None
        assert out["embedding"]["model"] in (CNN_MODEL, HISTOGRAM_MODEL)
        assert out["embedding"]["dimensions"] > 0
        assert out["ranked"][0]["item_id"] == candidate.id
        missing = analyze_image_against_registry(str(tmp_path / "none.png"), {}, [])
        assert missing["ok"] is False and "not found" in missing["error"]


# --------------------------------------------------------------------------
# 7. Evaluation harness (measured numbers only)
# --------------------------------------------------------------------------
class TestEvaluationHarness:
    def test_synthetic_dataset_can_be_measured(self, tmp_path):
        from app.utils.matcher_eval import (
            generate_synthetic_dataset, run_evaluation, format_report)
        root = tmp_path / "dataset"
        counts = generate_synthetic_dataset(str(root))
        assert sum(counts.values()) == 20
        metrics = run_evaluation(str(root))
        assert "error" not in metrics
        assert metrics["num_queries"] == 8 and metrics["num_gallery"] == 12
        for key in ("precision_at_1", "hit_at_3", "hit_at_5", "mrr"):
            assert 0.0 <= metrics[key] <= 1.0
        assert len(metrics["per_query"]) == metrics["num_queries"]
        report = format_report(metrics)
        assert "Measured results (this dataset only)" in report
        assert "not a" in report  # carries the no-general-accuracy disclaimer

    def test_empty_dataset_errors_instead_of_fabricating(self, tmp_path):
        from app.utils.matcher_eval import run_evaluation, format_report
        metrics = run_evaluation(str(tmp_path / "nothing"))
        assert "error" in metrics
        assert "could not run" in format_report(metrics)


# --------------------------------------------------------------------------
# 8. Notification history filtering
# --------------------------------------------------------------------------
class TestNotificationHistoryFilters:
    def test_category_filter_in_history(self, client, db, users):
        uid = users["student"].id
        Notification.notify(uid, title="Match note", message="m", category="match")
        Notification.notify(uid, title="Claim note", message="m", category="claim")
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        body = client.get("/notifications/?category=claim").get_data(as_text=True)
        # Inspect the main history list only - the navbar bell preview (global
        # context processor) always shows the latest notifications.
        start = body.index('list-group shadow-sm')
        region = body[start:start + 4000]
        assert "Claim note" in region
        assert "Match note" not in region
