"""
PHASE 10 TEST SUITE - Complete system testing and bug fixing audit.

Executes the mandated inspection list against the real codebase, focusing on
cross-cutting behaviour that earlier per-phase suites did not prove: role
landing routing, navigation search/route/street-view edge cases, upload
validation on EVERY surface, database constraints and real FK cascades,
transaction integrity during bulk import, notification delivery mechanics,
XSS escaping, and mobile-responsiveness structure. Payments stay sandbox-only:
no real money is transferred.
"""
import io
from datetime import datetime, timedelta

import pytest

from app.database import db
from app.models import (
    AuditLog, CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem,
    CampusFloorPlan, LostFoundItem, NavigationEdge, NavigationNode, Notification,
    Payment, Refund, User,
)
from tests.conftest import TEST_PASSWORD, login

VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"valid-test-image-body"
FAKE_IMAGE = b"<html><script>alert('pwn')</script> this is not an image!!"

ADMIN = "admin@gechassan.ac.in"
CANTEEN_ADMIN = "canteen@gechassan.ac.in"
STUDENT = "student@gechassan.ac.in"
TEACHER_VERIFIED = "teacher@gechassan.ac.in"
VISITOR = "visitor@gechassan.ac.in"


def _login_as(client, email):
    client.get("/auth/logout")
    return login(client, email)


def _seed_location(db, code, name, building="Block A", x=10, y=10, category="Classroom", **kw):
    node = NavigationNode(node_code=code, name=name, building=building,
                          floor="Ground Floor", category=category,
                          x_coord=x, y_coord=y, **kw)
    db.session.add(node)
    db.session.commit()
    return node


# ========================================= 1/2. authentication & role routing
class TestAuthenticationMatrix:

    @pytest.mark.parametrize("email,expected_prefix", [
        (ADMIN, "/admin/dashboard"),        # main_admin
        (CANTEEN_ADMIN, "/canteen-admin"),  # canteen operator
        (STUDENT, "/"),                     # student
        (TEACHER_VERIFIED, "/"),            # teacher
        (VISITOR, "/"),                     # visitor
    ])
    def test_each_role_lands_on_its_configured_home(self, client, app, users, email, expected_prefix):
        resp = login(client, email)
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith(expected_prefix)
        with client.session_transaction() as sess:
            assert sess.get("user_id")  # session established through ONE auth system

    def test_bad_credentials_never_create_session(self, client, app, users):
        resp = client.post("/auth/login", data={"email": STUDENT, "password": "WrongPass999"})
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert "user_id" not in sess
        assert AuditLog.query.filter_by(action="USER_LOGIN_FAILED").count() == 1

    def test_deactivated_user_cannot_login_any_role(self, client, app, users):
        resp = login(client, "inactive@gechassan.ac.in")
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert "user_id" not in sess
        assert AuditLog.query.filter_by(action="LOGIN_BLOCKED_INACTIVE").count() == 1


# ============================== 3/4/5. navigation search, routes, street view
class TestNavigationSystems:

    def test_search_data_api_returns_rich_location_records(self, client, app, users, db):
        _seed_location(db, "NODE_P10_SRCH", "CSE Lab 2", building="Block B",
                       category="Laboratory", photo_url="/static/images/placeholder_lab.jpg")
        payload = client.get("/navigation/api/nodes").get_json()
        match = [n for n in payload["nodes"] if n["node_code"] == "NODE_P10_SRCH"]
        assert match and match[0]["building"] == "Block B"
        assert match[0]["category"] == "Laboratory"
        assert "photo_url" in match[0]           # feeds map search + photo explore
        assert all(k in match[0] for k in ("x_coord", "y_coord", "name"))

    def test_route_api_edge_cases_handled_gracefully(self, client, app, users, db):
        a = _seed_location(db, "NODE_P10_RA", "Room A", x=0, y=0)
        assert client.post("/navigation/api/route", json={}).status_code == 400
        assert client.post("/navigation/api/route",
                           json={"start_node_id": a.id, "target_node_id": a.id}).status_code == 400
        assert client.post("/navigation/api/route",
                           json={"start_node_id": a.id, "target_node_id": 987654}).status_code == 404

    def test_street_view_directional_navigation_and_zoom_assets(self, client, app, users, db):
        a = _seed_location(db, "NODE_P10_SV1", "Corridor Start", x=10, y=10)
        b = _seed_location(db, "NODE_P10_SV2", "Corridor End", x=80, y=10)
        db.session.add(NavigationEdge(source_node_id=a.id, target_node_id=b.id,
                                      distance_meters=45.0, direction_hint="Straight ahead",
                                      is_bidirectional=True))
        db.session.commit()
        data = client.get(f"/navigation/api/node/{a.id}/connections").get_json()
        assert data["connection_count"] == 1
        conn = data["connections"][0]
        assert conn["direction_hint"] == "Straight ahead"
        assert conn["distance_meters"] == 45.0
        assert conn["traversable_back"] is True
        assert conn["node"]["name"] == "Corridor End"
        # the client-side photo-zoom / pan controller really ships with the app
        js = client.get("/static/js/navigation.js")
        assert js.status_code == 200
        body = js.get_data(as_text=True)
        assert "wheel" in body and "scale" in body  # mouse-wheel zoom + canvas scale
        html = client.get("/navigation/").get_data(as_text=True)
        assert "zoom" in html.lower()               # on-screen zoom controls


# ====================================== 8. notification delivery mechanics
class TestNotificationDelivery:

    def test_bell_delivery_read_and_mark_all_flow(self, client, app, users, db):
        assert _login_as(client, STUDENT).status_code == 302
        n = Notification(user_id=users["student"].id, title="Test delivery",
                        message="Check the bell", category="system", is_read=False)
        db.session.add(n)
        db.session.commit()

        listing = client.get("/notifications/").get_data(as_text=True)
        assert "Test delivery" in listing
        client.post(f"/notifications/mark-read/{n.id}")
        db.session.refresh(n)
        assert n.is_read is True

        db.session.add(Notification(user_id=users["student"].id, title="Second alert",
                                    message="bulk read check", category="canteen"))
        db.session.commit()
        client.post("/notifications/mark-all-read")
        assert Notification.query.filter_by(user_id=users["student"].id, is_read=False).count() == 0

        # category component filters canteen alerts
        assert "/notifications/?category=canteen" in client.get("/notifications/").get_data(as_text=True)

    def test_foreign_notification_cannot_be_touched(self, client, app, users, db):
        other = Notification(user_id=users["teacher_verified"].id, title="Private note",
                             message="not for students", category="admin")
        db.session.add(other)
        db.session.commit()
        assert _login_as(client, STUDENT).status_code == 302
        assert client.post(f"/notifications/mark-read/{other.id}").status_code == 403


# ================================== 10. menu & inventory validation surfaces
class TestMenuInventoryValidation:

    def _login_canteen(self, client, users):
        assert _login_as(client, CANTEEN_ADMIN).status_code == 302
        cat = CanteenCategory.query.first() or CanteenCategory(name="Meals", display_order=1)
        db.session.add(cat)
        db.session.commit()
        return cat

    def test_add_item_with_valid_photo_and_stock_decrement(self, client, app, users, db):
        cat = self._login_canteen(client, users)
        resp = client.post("/canteen-admin/menu", data={
            "action": "add_item", "name": "Paneer Thali", "category_id": str(cat.id),
            "price": "120", "stock_quantity": "30", "preparation_time_mins": "15",
            "photo": (io.BytesIO(VALID_PNG), "thali.png"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        item = CanteenItem.query.filter_by(name="Paneer Thali").one()
        assert item.photo_url and item.photo_url.startswith("/static/uploads/canteen/")
        assert item.stock_quantity == 30 and float(item.price) == 120.0

    def test_non_image_photo_rejected_on_menu_add(self, client, app, users, db):
        cat = self._login_canteen(client, users)
        resp = client.post("/canteen-admin/menu", data={
            "action": "add_item", "name": "Poison Item", "category_id": str(cat.id),
            "price": "10", "stock_quantity": "5",
            "photo": (io.BytesIO(FAKE_IMAGE), "evil.png"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        assert CanteenItem.query.filter_by(name="Poison Item").first() is None


# ================= 16. database constraints, FK cascades and transactions
class TestDatabaseConstraintsTransactions:

    def test_unique_constraints_enforced(self, db, users):
        from sqlalchemy.exc import IntegrityError
        dup = User(full_name="Dup", email=users["student"].email, role="student")
        dup.set_password(TEST_PASSWORD)
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        _seed_location(db, "NODE_P10_U", "Unique Room")
        with pytest.raises(IntegrityError):
            db.session.add(NavigationNode(node_code="NODE_P10_U", name="Clash",
                                          building="X", x_coord=0, y_coord=0))
            db.session.commit()
        db.session.rollback()

        # session is usable again after rollback (transaction integrity)
        ok = _seed_location(db, "NODE_P10_AFTER", "Still Works")
        assert ok.id

    def test_sqlite_foreign_keys_active_and_cascades_work(self, db):
        """Phase 10 BUG FIX proof: PRAGMA foreign_keys is ON and node deletion
        really removes its route connections (previously silent orphans)."""
        from sqlalchemy import text
        with db.engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

        a = _seed_location(db, "NODE_P10_C1", "Cascade Start")
        b = _seed_location(db, "NODE_P10_C2", "Cascade End")
        db.session.add(NavigationEdge(source_node_id=a.id, target_node_id=b.id,
                                      distance_meters=5.0))
        db.session.commit()
        assert NavigationEdge.query.count() == 1
        db.session.delete(a)
        db.session.commit()
        assert NavigationEdge.query.count() == 0  # cascaded, no orphan edges

    def test_invalid_foreign_reference_is_refused(self, db):
        from sqlalchemy.exc import IntegrityError
        real = _seed_location(db, "NODE_P10_FK", "FK Anchor")
        with pytest.raises(IntegrityError):
            db.session.add(NavigationEdge(source_node_id=real.id, target_node_id=424242,
                                          distance_meters=9.0))
            db.session.flush()
        db.session.rollback()

    def test_bulk_csv_import_transaction_isolates_bad_rows(self, client, app, users, db):
        """One malformed or duplicated row can never abort the whole import."""
        assert _login_as(client, ADMIN).status_code == 302
        csv_body = (
            "node_code,name,building,x_coord\n"
            "NODE_CSV_OK1,Good Room One,Block Z,10\n"
            "NODE_CSV_OK1,Good Room One duplicate,Block Z,20\n"       # dup inside file
            "NODE_CSV_BAD,Broken,Block Z,not-a-number\n"              # malformed coord
            "NODE_CSV_OK2,Good Room Two,Block Z,30\n"
        )
        resp = client.post("/admin/navigation/import", data={
            "kind": "nodes", "csv_file": (io.BytesIO(csv_body.encode()), "campus.csv"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        assert NavigationNode.query.filter_by(node_code="NODE_CSV_OK1").count() == 1
        assert NavigationNode.query.filter_by(node_code="NODE_CSV_OK2").count() == 1
        assert NavigationNode.query.filter_by(node_code="NODE_CSV_BAD").count() == 0

    def test_order_code_and_pickup_token_are_unique(self, db, users):
        from sqlalchemy.exc import IntegrityError
        cat = CanteenCategory(name="Snacks", display_order=9)
        db.session.add(cat); db.session.commit()
        pickup = datetime.utcnow() + timedelta(minutes=30)
        o1 = CanteenOrder(order_code="ORD-P10-UNIQUE-1", user_id=users["student"].id,
                          user_role_at_order="student", pickup_time=pickup,
                          total_amount=10, payment_status="paid", order_status="confirmed",
                          pickup_token="tok-a")
        db.session.add(o1); db.session.commit()
        with pytest.raises(IntegrityError):
            db.session.add(CanteenOrder(order_code="ORD-P10-UNIQUE-1",
                                        user_id=users["student"].id, user_role_at_order="student",
                                        pickup_time=pickup, total_amount=5,
                                        payment_status="pending", order_status="placed"))
            db.session.flush()
        db.session.rollback()
        with pytest.raises(IntegrityError):
            db.session.add(CanteenOrder(order_code="ORD-P10-UNIQUE-2",
                                        user_id=users["student"].id, user_role_at_order="student",
                                        pickup_time=pickup, total_amount=5,
                                        payment_status="pending", order_status="placed",
                                        pickup_token="tok-a"))
            db.session.flush()
        db.session.rollback()


# ============================= 17. upload validation on the navigation surface
class TestUploadValidationAllSurfaces:

    def test_navigation_rejects_non_image_despite_png_name(self, client, app, users, db):
        """Phase 10 BUG FIX proof: the admin photo upload validates content, not
        just the file extension (was extension-only before this phase)."""
        assert _login_as(client, ADMIN).status_code == 302
        resp = client.post("/admin/navigation/node/create", data={
            "node_code": "NODE_P10_UP", "name": "Upload Test Room", "building": "Block U",
            "x_coord": "5", "y_coord": "5",
            "photo": (io.BytesIO(FAKE_IMAGE), "malicious.png"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        node = NavigationNode.query.filter_by(node_code="NODE_P10_UP").one()
        assert node.photo_url is None                      # nothing stored
        # ...while a real PNG header is accepted normally
        resp = client.post(f"/admin/navigation/node/{node.id}/update", data={
            "name": "Upload Test Room", "building": "Block U",
            "photo": (io.BytesIO(VALID_PNG), "good.png"),
        }, content_type="multipart/form-data")
        db.session.refresh(node)
        assert node.photo_url and node.photo_url.startswith("/static/uploads/navigation/")

    def test_lost_found_rejects_non_image_report_photo(self, client, app, users, db):
        assert _login_as(client, STUDENT).status_code == 302
        before = LostFoundItem.query.count()
        resp = client.post("/lost-found/report", data={
            "report_type": "lost", "title": "Fake Photo Case", "category": "Electronics",
            "location_reported": "Lab", "description": "should be rejected",
            "photo": (io.BytesIO(FAKE_IMAGE), "nope.png"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        assert LostFoundItem.query.count() == before       # content validation refused it

    def test_csv_import_requires_csv_extension(self, client, app, users, db):
        assert _login_as(client, ADMIN).status_code == 302
        resp = client.post("/admin/navigation/import", data={
            "kind": "nodes", "csv_file": (io.BytesIO(b"a,b\n1,2"), "payload.exe"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 302
        assert AuditLog.query.filter_by(action="NAV_DATA_IMPORTED").count() == 0


# ===================================== 18. security protections (XSS, access)
class TestSecurityProtections:

    def test_input_is_escaped_not_executed(self, client, app, users, db):
        assert _login_as(client, STUDENT).status_code == 302
        client.post("/lost-found/report", data={
            "report_type": "found", "title": "<script>alert(1)</script>",
            "category": "Other", "location_reported": "Gate",
            "description": "<img src=x onerror=alert(2)>",
        })
        item = LostFoundItem.query.order_by(LostFoundItem.id.desc()).one()
        assert "<script>" in item.title  # stored verbatim...
        html = client.get("/lost-found/").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html    # ...but never rendered raw
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_all_admin_writes_reject_get_method(self, client, app, users, db):
        """State-changing endpoints are POST-only (no CSRF-free GET mutations)."""
        assert _login_as(client, ADMIN).status_code == 302
        node = _seed_location(db, "NODE_P10_GET", "GET Guard Room")
        assert client.get(f"/admin/navigation/node/{node.id}/delete").status_code == 405
        assert client.get(f"/admin/users/{users['student'].id}/toggle-status").status_code == 405
        assert client.get("/admin/canteen/item/1/update", data={"price": "1"}).status_code == 405

    def test_error_pages_never_leak_and_honor_role_view(self, client, app, users, db):
        resp = client.get("/navigation/api/node/999999")          # anonymous API 404
        assert resp.status_code == 404
        assert _login_as(client, STUDENT).status_code == 302
        resp = client.get("/admin/dashboard")                     # student hits 403/redirect
        assert resp.status_code == 302                            # redirected, no leak


# ============================== 19. mobile responsiveness (structural proofs)
class TestMobileResponsiveness:

    @pytest.mark.parametrize("path", ["/", "/navigation/", "/lost-found/", "/canteen/",
                                      "/auth/login", "/canteen/cart"])
    def test_viewport_meta_present(self, client, app, users, path):
        html = client.get(path, follow_redirects=True).get_data(as_text=True)
        assert 'name="viewport"' in html and "width=device-width" in html

    def test_responsive_css_infrastructure_ships(self, client, app):
        base = client.get("/static/css/style.css")
        dash = client.get("/static/css/dashboard.css")
        assert base.status_code == 200 and dash.status_code == 200
        assert "@media" in dash.get_data(as_text=True)     # breakpoints for the portal
        html = client.get("/auth/login").get_data(as_text=True)
        assert "navbar-toggler" in html                     # collapsible mobile navbar

    def test_admin_tables_scroll_instead_of_breaking(self, client, app, users, db):
        assert _login_as(client, ADMIN).status_code == 302
        for path in ("/admin/canteen", "/admin/reports", "/admin/users",
                     "/admin/audit-logs", "/admin/navigation/manage"):
            html = client.get(path).get_data(as_text=True)
            assert "table-responsive" in html, f"{path} needs responsive tables"
