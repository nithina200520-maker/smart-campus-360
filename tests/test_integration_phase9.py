"""
PHASE 9 TEST SUITE - Complete integration of all three modules.

Proves the platform runs as ONE system: one authentication system, one shared
backend, one shared database, one Main Admin dashboard, one restricted Canteen
Admin dashboard, consistent roles/permissions that apply live, consistent
notification components, a consistent responsive interface, and no duplicated
implementations. Cross-module workflows are exercised end-to-end for the
student, teacher and visitor experiences. All canteen payments remain in
sandbox/test mode: no real money is transferred.
"""
import app.blueprints.canteen.routes as canteen_routes
from app.database import db
from app.models import (
    AuditLog, CanteenCategory, CanteenItem, CanteenOrder, LostFoundItem,
    Notification, NavigationEdge, NavigationNode, Payment, Refund, User,
)
from tests.conftest import login

ADMIN = "admin@gechassan.ac.in"
CANTEEN_ADMIN = "canteen@gechassan.ac.in"
STUDENT = "student@gechassan.ac.in"
TEACHER_PENDING = "pending.teacher@gechassan.ac.in"
VISITOR = "visitor@gechassan.ac.in"


def _login_as(client, email):
    client.get("/auth/logout")
    return login(client, email)


def _seed_location(db, code, name, building="Block A", x=10, y=10, **kw):
    node = NavigationNode(node_code=code, name=name, building=building,
                          floor="Ground Floor", category="Classroom",
                          x_coord=x, y_coord=y, **kw)
    db.session.add(node)
    db.session.commit()
    return node


def _seed_menu(db, stock=50, price=45.00):
    cat = CanteenCategory.query.first() or CanteenCategory(name="Breakfast", display_order=1)
    db.session.add(cat)
    db.session.commit()
    item = CanteenItem(category_id=cat.id, name="Masala Dosa", description="Tasty dosa",
                       price=price, stock_quantity=stock, preparation_time_mins=10)
    db.session.add(item)
    db.session.commit()
    return item


def _paid_order(client, monkeypatch, item, email=STUDENT, qty=1):
    _login_as(client, email)
    monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
    with client.session_transaction() as sess:
        sess["canteen_cart"] = {str(item.id): qty}
    resp = client.post("/canteen/checkout", data={"payment_method": "upi_simulation"})
    assert resp.status_code == 302
    return CanteenOrder.query.order_by(CanteenOrder.id.desc()).first()


# ===================================================== one backend / one DB
class TestSinglePlatformCore:

    def test_one_database_shared_by_all_modules(self, app, db):
        """Every model of every module is bound to the same engine/metadata."""
        bind = db.session.get_bind()
        assert bind is db.engine
        for model in (User, NavigationNode, NavigationEdge, LostFoundItem,
                      CanteenOrder, CanteenItem, Payment, Refund,
                      Notification, AuditLog):
            assert model.query.session.get_bind() is bind
        for table in ("navigation_nodes", "lost_found_items", "canteen_orders",
                      "payments", "refunds", "notifications", "audit_logs", "users"):
            assert table in db.metadata.tables

    def test_single_backend_app_registers_all_blueprints_once(self, app):
        names = sorted(app.blueprints.keys())
        assert names == ["admin", "auth", "canteen", "canteen_admin", "lost_found",
                         "main", "navigation", "notifications"]
        # No duplicated implementations: every URL path is owned by exactly one
        # endpoint (one page, one handler - across the entire unified platform).
        owners = {}
        for rule in app.url_map.iter_rules():
            if rule.endpoint == "static":
                continue
            owners.setdefault(str(rule.rule), set()).add(rule.endpoint)
        duplicated = {path: eps for path, eps in owners.items() if len(eps) > 1}
        assert duplicated == {}

    def test_one_authentication_system(self, app):
        auth_endpoints = sorted({r.endpoint for r in app.url_map.iter_rules()
                                 if r.endpoint and r.endpoint.split(".")[-1] in
                                 ("login", "logout", "register")})
        assert auth_endpoints == ["auth.login", "auth.logout", "auth.register"]


# =========================================== one auth system across modules
class TestOneAuthSystem:

    def test_one_login_unlocks_every_module_and_logout_closes_all(self, client, app, users):
        resp = client.post("/auth/register", data={
            "full_name": "Integration Fresher", "email": "fresher@gechassan.ac.in",
            "password": "Freshpass123", "confirm_password": "Freshpass123",
            "role": "student", "department": "CSE", "phone": "9998887776",
            "usn": "4GH24CS999", "semester": "1st Semester",
        })
        assert resp.status_code == 302
        assert User.query.filter_by(email="fresher@gechassan.ac.in").one().role == "student"

        assert login(client, "fresher@gechassan.ac.in", "Freshpass123").status_code == 302
        for path in ("/navigation/", "/lost-found/", "/canteen/", "/canteen/cart",
                     "/canteen/my-orders", "/lost-found/my-reports", "/notifications/",
                     "/auth/profile"):
            assert client.get(path).status_code == 200, f"single session must open {path}"

        client.get("/auth/logout")
        for path in ("/canteen/my-orders", "/lost-found/my-reports",
                     "/notifications/", "/auth/profile"):
            resp = client.get(path)
            assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]

    def test_public_registration_can_never_create_admins(self, client, app, users):
        resp = client.post("/auth/register", data={
            "full_name": "Wannabe Admin", "email": "wannabe@gechassan.ac.in",
            "password": "Wrongdoer123", "confirm_password": "Wrongdoer123",
            "role": "main_admin",
        })
        assert resp.status_code == 302
        assert User.query.filter_by(email="wannabe@gechassan.ac.in").first() is None
        assert AuditLog.query.filter_by(action="UNAUTHORIZED_ADMIN_REGISTRATION_ATTEMPT").count() == 1


# ==================================================== student full journey
class TestStudentCrossModuleJourney:

    def test_search_route_photo_report_order_pickup_refund(self, client, app, users, db, monkeypatch):
        # --- shared campus data (Module 1) ---
        gate = _seed_location(db, "NODE_P9_GATE", "Main Gate", x=10, y=10,
                              photo_url="/static/images/placeholder_gate.jpg")
        lib = _seed_location(db, "NODE_P9_LIB", "Central Library", building="Block B", x=90, y=60)
        db.session.add(NavigationEdge(source_node_id=gate.id, target_node_id=lib.id,
                                      distance_meters=120.0, is_bidirectional=True))
        db.session.commit()

        assert _login_as(client, STUDENT).status_code == 302

        # search + route following over the shared map graph
        nodes = client.get("/navigation/api/nodes").get_json()["nodes"]
        assert {n["id"] for n in nodes} >= {gate.id, lib.id}
        route = client.post("/navigation/api/route",
                            json={"start_node_id": gate.id, "target_node_id": lib.id})
        assert route.status_code == 200 and route.get_json()["success"] is True

        # photograph exploration (street-view detail API on the shared backend)
        detail = client.get(f"/navigation/api/node/{lib.id}")
        assert detail.status_code == 200

        # --- Lost & Found report (Module 2) through the same session ---
        resp = client.post("/lost-found/report", data={
            "report_type": "lost", "title": "Blue Water Bottle",
            "category": "Personal Items", "location_reported": "Central Library",
            "description": "Steel bottle with a sticker", "contact_phone": "9999999999",
        })
        assert resp.status_code == 302
        item = LostFoundItem.query.filter_by(title="Blue Water Bottle").one()
        assert item.user_id == users["student"].id
        assert "Blue Water Bottle" in client.get("/lost-found/my-reports").get_data(as_text=True)

        # --- canteen order (Module 3) through the same session ---
        food = _seed_menu(db)
        monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
        with client.session_transaction() as sess:
            sess["canteen_cart"] = {str(food.id): 1}
        assert client.post("/canteen/checkout",
                           data={"payment_method": "upi_simulation"}).status_code == 302
        order = CanteenOrder.query.order_by(CanteenOrder.id.desc()).first()
        assert order.user_id == users["student"].id
        assert order.payment.status == "succeeded"  # sandbox capture, no real money
        assert order.pickup_token                    # QR pickup credential exists

        # canteen staff moves the order forward; the student tracks it
        _login_as(client, CANTEEN_ADMIN)
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "preparing"})
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "ready"})

        _login_as(client, STUDENT)
        my_orders = client.get("/canteen/my-orders").get_data(as_text=True)
        assert order.order_code in my_orders

        # QR-based collection: counter scans the pickup payload (one redemption)
        _login_as(client, CANTEEN_ADMIN)
        payload = f"SC360-PICKUP:{order.order_code}:{order.pickup_token}"
        client.post("/canteen-admin/verify-pickup", data={"order_code": payload})
        db.session.refresh(order)
        assert order.order_status == "collected"
        client.post("/canteen-admin/verify-pickup", data={"order_code": payload})
        db.session.refresh(order)
        assert order.order_status == "collected"  # duplicate redemption refused

        # --- eligible refund tracking (Phase 7 pipeline, shared session) ---
        order2 = _paid_order(client, monkeypatch, food, qty=2)
        order2.order_status = "preparing"
        db.session.commit()
        _login_as(client, STUDENT)
        client.post(f"/canteen/order/{order2.id}/request-refund",
                    data={"refund_reason": "Cannot pick up anymore"})
        _login_as(client, ADMIN)
        client.post(f"/canteen-admin/orders/{order2.id}/refund",
                    data={"amount": "90.00", "refund_reason": "Approved full refund"})
        db.session.refresh(order2)
        assert order2.order_status == "refunded"
        refund = Refund.query.filter_by(order_id=order2.id).one()
        assert refund.status == "succeeded" and refund.refund_reference

        # student sees the refund trail on their own order page
        _login_as(client, STUDENT)
        detail_html = client.get(f"/canteen/order/{order2.order_code}").get_data(as_text=True)
        assert refund.refund_reference in detail_html or "Refund" in detail_html

        # --- relevant notifications, one shared component ---
        titles = [n.title for n in Notification.query.filter_by(user_id=users["student"].id).all()]
        assert any("ready" in t.lower() or "pickup" in t.lower() for t in titles)
        assert any("refund" in t.lower() for t in titles)
        filtered = client.get("/notifications/?category=canteen").get_data(as_text=True)
        assert "Order" in filtered

    def test_home_page_reflects_all_three_modules(self, client, app, users, db, monkeypatch):
        node = _seed_location(db, "NODE_P9_HALL", "Auditorium Hall", building="Block C")
        food = _seed_menu(db)
        _paid_order(client, monkeypatch, food)
        client.post("/lost-found/report", data={
            "report_type": "found", "title": "Keys with Red Tag", "category": "Personal Items",
            "location_reported": "Auditorium Hall", "description": "Set of keys found"})
        client.get("/auth/logout")
        html = client.get("/").get_data(as_text=True)
        # genuine cross-module activity on one landing page
        assert "Auditorium Hall" in html          # navigation data (quick location finder)
        assert "Keys with Red Tag" in html        # lost & found activity feed
        assert "Order" in html                    # canteen activity feed


# ==================================================== teacher experience
class TestTeacherExperience:

    def test_navigation_and_lost_found_available_priority_only_when_verified(self, client, app, users, db, monkeypatch):
        assert _login_as(client, TEACHER_PENDING).status_code == 302
        # shared navigation + lost & found features work for teachers
        assert client.get("/navigation/").status_code == 200
        assert client.get("/lost-found/").status_code == 200

        food = _seed_menu(db, stock=100)
        order = _paid_order(client, monkeypatch, food, email=TEACHER_PENDING)
        assert order.is_priority is False  # unverified: no configured priority

        _login_as(client, ADMIN)
        client.post(f"/admin/users/{users['teacher_pending'].id}/verify-teacher")
        db.session.refresh(users["teacher_pending"])
        assert users["teacher_pending"].is_verified is True

        order2 = _paid_order(client, monkeypatch, food, email=TEACHER_PENDING)
        assert order2.is_priority is True   # verified: teacher-first priority

        # students in the same queue stay standard
        order3 = _paid_order(client, monkeypatch, food, email=STUDENT)
        assert order3.is_priority is False


# ==================================================== visitor experience
class TestVisitorExperience:

    def test_visitors_get_public_navigation_and_no_private_data(self, client, app, users, db):
        _seed_location(db, "NODE_P9_VIS", "Visitor Gallery", building="Block A")
        assert _login_as(client, VISITOR).status_code == 302

        # permitted public features
        assert client.get("/navigation/").status_code == 200
        assert client.get("/lost-found/").status_code == 200
        assert client.get("/canteen/").status_code == 200
        assert "Visitor Gallery" in client.get("/navigation/").get_data(as_text=True)

        # restricted private participation (consistent restrict_visitors component)
        resp = client.get("/lost-found/report")
        assert resp.status_code == 302 and "/navigation/" in resp.headers["Location"]

        item = LostFoundItem(user_id=users["student"].id, report_type="found",
                             title="Student Calculator", category="Electronics",
                             location_reported="Lab", description="Casio", status="open")
        db.session.add(item); db.session.commit()
        resp = client.post(f"/lost-found/item/{item.id}/claim",
                           data={"proof_statement": "I saw it"})
        assert resp.status_code == 302 and "/navigation/" in resp.headers["Location"]

        # no admin surfaces in the visitor chrome
        html = client.get("/").get_data(as_text=True)
        assert "Main Admin Hub" not in html and "/admin/dashboard" not in html


# ==================================== one dashboard per admin + live roles
class TestDashboardTopologyAndLiveRoles:

    def test_exactly_one_main_and_one_restricted_canteen_dashboard(self, app):
        dashboards = sorted({r.endpoint for r in app.url_map.iter_rules()
                             if r.rule.rstrip("/").endswith("/dashboard")})
        assert dashboards == ["admin.dashboard", "canteen_admin.dashboard"]

    def test_main_admin_single_hub_reaches_all_modules(self, client, app, users, db):
        assert _login_as(client, ADMIN).status_code == 302
        for path in ("/admin/dashboard", "/admin/navigation/manage", "/admin/lost-found",
                     "/admin/canteen", "/admin/reports", "/admin/users",
                     "/canteen-admin/dashboard"):
            assert client.get(path).status_code == 200, f"Main Admin hub must cover {path}"

    def test_canteen_admin_dashboard_stays_restricted(self, client, app, users, db):
        assert _login_as(client, CANTEEN_ADMIN).status_code == 302
        assert client.get("/canteen-admin/dashboard").status_code == 200
        for path in ("/admin/dashboard", "/admin/users", "/admin/canteen", "/admin/reports",
                     "/admin/navigation/manage"):
            resp = client.get(path)
            assert resp.status_code == 302 and "/admin" not in resp.headers["Location"]

    def test_role_permissions_apply_live_without_relogin(self, client, app, users, db):
        """Consistent RBAC: authorization reads the live DB role each request."""
        visitor_client = app.test_client()
        assert login(visitor_client, VISITOR).status_code == 302
        # visitors are restricted from private reporting
        resp = visitor_client.get("/lost-found/report")
        assert resp.status_code == 302

        assert _login_as(client, ADMIN).status_code == 302
        client.post(f"/admin/users/{users['visitor'].id}/change-role",
                    data={"new_role": "teacher"})

        # SAME session cookie (no re-login) now behaves as a teacher account
        resp = visitor_client.get("/lost-found/report")
        assert resp.status_code == 200
        with visitor_client.session_transaction() as sess:
            assert sess["user_id"] == users["visitor"].id  # never re-authenticated

        # revocation: back to visitor -> restricted again, still without re-login
        _login_as(client, ADMIN)
        client.post(f"/admin/users/{users['visitor'].id}/change-role",
                    data={"new_role": "visitor"})
        resp = visitor_client.get("/lost-found/report")
        assert resp.status_code == 302 and "/navigation/" in resp.headers["Location"]

    def test_deactivation_terminates_live_sessions_platform_wide(self, client, app, users, db):
        """Consistent security: one suspension cuts every module session at once."""
        student_client = app.test_client()
        assert login(student_client, STUDENT).status_code == 302
        assert student_client.get("/notifications/").status_code == 200
        assert student_client.get("/canteen/my-orders").status_code == 200

        assert _login_as(client, ADMIN).status_code == 302
        client.post(f"/admin/users/{users['student'].id}/toggle-status")

        # the student's existing session is invalidated across all modules
        for path in ("/notifications/", "/canteen/my-orders", "/lost-found/my-reports",
                     "/auth/profile"):
            resp = student_client.get(path)
            assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]

        # and re-login is refused with an audit entry
        resp = login(student_client, STUDENT)
        assert resp.status_code == 200  # back to the login form, no session
        with student_client.session_transaction() as sess:
            assert "user_id" not in sess
        assert AuditLog.query.filter_by(action="LOGIN_BLOCKED_INACTIVE").count() >= 1


# ==================================== consistent responsive interface parts
class TestConsistentInterface:

    def test_shared_navbar_links_all_modules_on_every_base_page(self, client, app, users, db):
        _seed_location(db, "NODE_P9_NAV", "Convocation Hall")
        for path in ("/about", "/navigation/", "/lost-found/", "/canteen/", "/auth/login"):
            html = client.get(path).get_data(as_text=True)
            assert 'Campus Navigation' in html, f"{path} must link the navigation module"
            assert 'AI Lost & Found' in html, f"{path} must link the lost & found module"
            assert 'Smart Canteen' in html, f"{path} must link the canteen module"

    def test_public_map_hides_unpublished_locations_everywhere(self, client, app, users, db):
        hidden = _seed_location(db, "NODE_P9_HIDDEN", "Server Room ST-9")
        _login_as(client, ADMIN)
        client.post(f"/admin/navigation/node/{hidden.id}/toggle-publish")
        client.get("/auth/logout")
        assert "Server Room ST-9" not in client.get("/").get_data(as_text=True)
        assert "Server Room ST-9" not in client.get("/navigation/").get_data(as_text=True)
        ids = [n["id"] for n in client.get("/navigation/api/nodes").get_json()["nodes"]]
        assert hidden.id not in ids
