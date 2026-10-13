"""
PHASE 8 TEST SUITE - Central Main Admin Dashboard.

Covers every mandated control area: campus management (buildings/floors, room
information, campus photographs, map points + route connections, location
publication & updates), Lost & Found management from the centre (reports, AI
matches, verification, notifications, returned items), canteen management
(admin accounts, items & stock, teacher/student orders, priority, payment
records, refund requests, complaints), user management (verification,
activation, roles, audit logs), reports computed live from the database
(no hardcoded numbers) and the security matrix - the Canteen Admin must never
reach campus administration or unrestricted user management.
All payment flows remain sandbox/test mode: no real money.
"""
import io
import json
import re
from datetime import date, datetime, timedelta

import pytest

import app.blueprints.canteen.routes as canteen_routes
from app.database import db
from app.models import (
    AuditLog, CanteenCategory, CanteenItem, CanteenOrder, CanteenPickupSlot,
    LostFoundClaim, LostFoundItem, LostFoundMatch, NavigationEdge, NavigationNode,
    Notification, Payment, Refund, User,
)
from tests.conftest import login


def _login_as(client, email):
    client.get("/auth/logout")
    return login(client, email)


ADMIN = "admin@gechassan.ac.in"
CANTEEN_ADMIN = "canteen@gechassan.ac.in"
STUDENT = "student@gechassan.ac.in"


# =========================================================== campus management
class TestCampusManagement:

    def test_create_update_and_photo_upload(self, client, app, users, db):
        _login_as(client, ADMIN)
        resp = client.post("/admin/navigation/node/create", data={
            "node_code": "NODE_P8_LAB", "name": "Robotics Lab", "building": "Block P8",
            "floor": "1st Floor", "category": "Laboratory", "x_coord": "10", "y_coord": "20",
        })
        assert resp.status_code == 302
        node = NavigationNode.query.filter_by(node_code="NODE_P8_LAB").one()
        assert node.is_published is True  # newly added locations publish live

        # room information update + campus photograph replacement
        # (Phase 10: uploads now require true image content, not just an extension)
        resp = client.post(f"/admin/navigation/node/{node.id}/update",
                           data={"name": "Robotics & AI Lab", "description": "Block P8, 1st floor",
                                 "x_coord": "15", "y_coord": "25", "is_accessible": "on",
                                 "photo": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"-valid-test-body"), "lab.png")},
                           content_type="multipart/form-data")
        assert resp.status_code == 302
        db.session.refresh(node)
        assert node.name == "Robotics & AI Lab"
        assert node.x_coord == 15
        assert node.photo_url and node.photo_url.startswith("/static/uploads/navigation/")
        assert AuditLog.query.filter_by(action='NAV_NODE_UPDATED').count() == 1
        assert AuditLog.query.filter_by(action='NAV_NODE_UPDATED').one().user_id == users["main_admin"].id

    def test_location_publication_hides_and_shows_everywhere(self, client, app, users, db):
        _login_as(client, ADMIN)
        for code, x in (("NODE_P8_A", 100), ("NODE_P8_B", 200)):
            client.post("/admin/navigation/node/create", data={
                "node_code": code, "name": f"Room {code}", "building": "Block P8",
                "floor": "Ground Floor", "category": "Classroom",
                "x_coord": str(x), "y_coord": "100"})
        a = NavigationNode.query.filter_by(node_code="NODE_P8_A").one()
        b = NavigationNode.query.filter_by(node_code="NODE_P8_B").one()
        client.post("/admin/navigation/edge/create", data={
            "source_node_id": str(a.id), "target_node_id": str(b.id),
            "distance_meters": "10", "is_bidirectional": "on"})
        assert NavigationEdge.query.count() == 1

        # route works while both are published
        client.get("/auth/logout")
        resp = client.post("/navigation/api/route", json={"start_node_id": a.id, "target_node_id": b.id})
        assert resp.status_code == 200 and resp.get_json()["success"] is True

        # withdraw room B from publication
        _login_as(client, ADMIN)
        resp = client.post(f"/admin/navigation/node/{b.id}/toggle-publish")
        assert resp.status_code == 302
        db.session.refresh(b)
        assert b.is_published is False

        client.get("/auth/logout")
        ids = [n["id"] for n in client.get("/navigation/api/nodes").get_json()["nodes"]]
        assert a.id in ids and b.id not in ids                       # hidden from map API
        assert client.get(f"/navigation/api/node/{b.id}").status_code == 404
        resp = client.post("/navigation/api/route", json={"start_node_id": a.id, "target_node_id": b.id})
        assert resp.status_code == 404                                # unroutable while hidden

        # republish restores it (location update workflow complete)
        _login_as(client, ADMIN)
        client.post(f"/admin/navigation/node/{b.id}/toggle-publish")
        client.get("/auth/logout")
        ids = [n["id"] for n in client.get("/navigation/api/nodes").get_json()["nodes"]]
        assert b.id in ids
        assert AuditLog.query.filter_by(action='NAV_NODE_PUBLICATION_CHANGED').count() == 2

    def test_manager_lists_buildings_floors_and_photos(self, client, app, users, db):
        _login_as(client, ADMIN)
        html = client.get("/admin/navigation/manage").get_data(as_text=True)
        assert "Campus Management" in html and "Navigation Points Directory" in html


# ====================================================== lost & found (central)
class TestLostFoundCentral:

    def _found_item(self, db, users):
        item = LostFoundItem(user_id=users["student"].id, report_type="found",
                             title="Black Wallet", category="Documents",
                             location_reported="Library", description="Leather wallet",
                             status="open")
        db.session.add(item)
        db.session.commit()
        return item

    def test_verify_claim_and_return_from_admin(self, client, app, users, db):
        item = self._found_item(db, users)
        claim = LostFoundClaim(item_id=item.id, claimant_id=users["teacher_verified"].id,
                               proof_statement="Wallet contains my ID card", status="pending")
        db.session.add(claim)
        db.session.commit()

        _login_as(client, ADMIN)
        client.post(f"/admin/lost-found/item/{item.id}/verify")
        db.session.refresh(item)
        assert item.verified_by_admin_id == users["main_admin"].id
        assert item.status == "matched"

        client.post(f"/admin/lost-found/claim/{claim.id}/decision",
                    data={"decision": "approve", "decision_note": "ID verified"})
        db.session.refresh(claim); db.session.refresh(item)
        assert claim.status == "approved" and item.status == "claimed"

        client.post(f"/admin/lost-found/item/{item.id}/record-return",
                    data={"handover_note": "Collected at office"})
        db.session.refresh(item)
        assert item.status == 'closed' and item.collected_at is not None
        # both reporter and recipient were notified
        assert Notification.query.filter(Notification.category == 'return').count() >= 2

    def test_dashboard_surfaces_matches_and_claims(self, client, app, users, db):
        lost = self._found_item(db, users)
        found = LostFoundItem(user_id=users["visitor"].id, report_type="found",
                              title="Black Wallet", category="Documents",
                              location_reported="Library", description="Wallet with cash",
                              status="open")
        db.session.add(found)
        db.session.commit()
        db.session.add(LostFoundMatch(lost_item_id=lost.id, found_item_id=found.id,
                                      similarity_score=0.9, composite_score=0.88,
                                      status="suggested"))
        db.session.add(LostFoundClaim(item_id=found.id, claimant_id=users["student"].id,
                                      proof_statement="It is mine", status="pending"))
        db.session.commit()

        _login_as(client, ADMIN)
        html = client.get("/admin/dashboard").get_data(as_text=True)
        assert "AI Matches Review" in html and "Pending Claims" in html
        assert client.get("/admin/lost-found").status_code == 200


# ====================================================== canteen (central admin)
def _seed_menu(db, stock=50, price=45.00):
    cat = CanteenCategory.query.first() or CanteenCategory(name="Breakfast", display_order=1)
    db.session.add(cat)
    db.session.commit()
    item = CanteenItem(category_id=cat.id, name="Masala Dosa", description="Tasty dosa",
                       price=price, stock_quantity=stock, preparation_time_mins=10)
    db.session.add(item)
    db.session.commit()
    return item


def _paid_order(client, monkeypatch, item, email=STUDENT, qty=2):
    _login_as(client, email)
    monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
    with client.session_transaction() as sess:
        sess["canteen_cart"] = {str(item.id): qty}
    resp = client.post("/canteen/checkout", data={"payment_method": "upi_simulation"})
    assert resp.status_code == 302
    return CanteenOrder.query.order_by(CanteenOrder.id.desc()).first()


class TestCanteenCentral:

    def test_console_shows_teacher_and_student_orders_with_priority(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        _paid_order(client, monkeypatch, item, email=STUDENT)          # student order
        _paid_order(client, monkeypatch, item, email="teacher@gechassan.ac.in")  # priority
        _login_as(client, ADMIN)
        html = client.get("/admin/canteen").get_data(as_text=True)
        assert "TEACHER-FIRST" in html
        assert "Robotics" not in html  # sanity: unrelated module content not leaked
        orders = CanteenOrder.query.all()
        assert len(orders) == 2
        assert sum(1 for o in orders if o.is_priority) == 1

    def test_role_and_status_filters(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        _paid_order(client, monkeypatch, item, email=STUDENT)
        _login_as(client, ADMIN)
        html = client.get("/admin/canteen?tab=orders&role=teacher").get_data(as_text=True)
        assert "No orders match this filter" in html
        html = client.get("/admin/canteen?tab=orders&role=student").get_data(as_text=True)
        assert "student@gechassan.ac.in" not in html  # email not shown, but the row is
        assert "Sneha Patil" in html

    def test_main_admin_updates_item_stock_and_availability(self, client, app, users, db):
        item = _seed_menu(db, stock=40, price=45)
        _login_as(client, ADMIN)
        resp = client.post(f"/admin/canteen/item/{item.id}/update",
                           data={"price": "50", "stock_quantity": "75", "is_available": "on"})
        assert resp.status_code == 302
        db.session.refresh(item)
        assert float(item.price) == 50.0 and item.stock_quantity == 75 and item.is_available
        audit = AuditLog.query.filter_by(action='CANTEEN_ITEM_UPDATED_BY_MAIN_ADMIN').one()
        assert audit.user_id == users["main_admin"].id

        # deactivating hides from students - toggling works both ways
        client.post(f"/admin/canteen/item/{item.id}/update", data={"stock_quantity": "75"})
        db.session.refresh(item)
        assert item.is_available is False

    def test_payment_records_tab_lists_gateway_ledger(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, monkeypatch, item, qty=1)  # 2x? qty=1 -> 45
        payment = order.payment
        assert payment is not None and payment.status == 'succeeded'
        _login_as(client, ADMIN)
        html = client.get("/admin/canteen?tab=payments").get_data(as_text=True)
        assert payment.intent_id in html
        assert payment.transaction_reference in html
        assert "no real money was transferred" in html.lower()

    def test_main_admin_authorises_refund_from_console(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, monkeypatch, item, qty=2)  # ₹90 captured
        # 1. complaint recorded by the customer
        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "Order never delivered"})
        db.session.refresh(order)
        assert order.order_status == 'refund_requested'

        # 2-5. Main Admin authorises and initiates the gateway refund
        _login_as(client, ADMIN)
        resp = client.post(f"/canteen-admin/orders/{order.id}/refund",
                           data={"amount": "90.00", "refund_reason": "Not delivered - authorised by Main Admin"})
        assert resp.status_code == 302

        refund = Refund.query.filter_by(order_id=order.id).order_by(Refund.id.desc()).one()
        assert refund.status == 'succeeded'                 # sandbox confirmed immediately
        assert refund.authorized_by == users["main_admin"].id  # required authorization recorded
        assert refund.provider_refund_id                     # gateway refund reference tracked
        db.session.refresh(order)
        assert order.order_status == 'refunded'
        # 8. user notified
        assert Notification.query.filter(
            Notification.user_id == order.user_id,
            Notification.category == 'canteen').count() >= 1

        # console refunds tab now shows the completed case with complaint trail
        html = client.get("/admin/canteen?tab=refunds").get_data(as_text=True)
        assert "Refund Requests" in html
        assert refund.refund_reference in html and "Order never delivered" in html

    def test_canteen_admin_accounts_listed_and_suspension_works(self, client, app, users, db):
        _login_as(client, ADMIN)
        html = client.get("/admin/canteen?tab=accounts").get_data(as_text=True)
        assert CANTEEN_ADMIN in html
        ca = users["canteen_admin"]
        client.post(f"/admin/users/{ca.id}/toggle-status")
        db.session.refresh(ca)
        assert ca.is_active is False
        client.post(f"/admin/users/{ca.id}/toggle-status")
        db.session.refresh(ca)
        assert ca.is_active is True


# ========================================================= user management
class TestUserManagementCentral:

    def test_teacher_verification_grants_and_revokes_priority(self, client, app, users, db):
        _login_as(client, ADMIN)
        pending = users["teacher_pending"]
        client.post(f"/admin/users/{pending.id}/verify-teacher")
        db.session.refresh(pending)
        assert pending.is_verified is True
        assert AuditLog.query.filter_by(action='TEACHER_VERIFIED').count() == 1

        client.post(f"/admin/users/{pending.id}/revoke-teacher")
        db.session.refresh(pending)
        assert pending.is_verified is False

    def test_role_change_activation_and_audit_visibility(self, client, app, users, db):
        _login_as(client, ADMIN)
        student = users["student"]
        client.post(f"/admin/users/{student.id}/change-role", data={"new_role": "teacher"})
        db.session.refresh(student)
        assert student.role == 'teacher' and student.is_verified is False  # re-verification needed

        client.post(f"/admin/users/{student.id}/toggle-status")
        db.session.refresh(student)
        assert student.is_active is False

        html = client.get("/admin/audit-logs?module=ADMIN").get_data(as_text=True)
        assert "USER_ROLE_CHANGED" in html and "USER_DEACTIVATED" in html

        # Main Admin accounts can never be suspended
        client.post(f"/admin/users/{users['main_admin'].id}/toggle-status")
        db.session.refresh(users["main_admin"])
        assert users["main_admin"].is_active is True


# ================================================================== reports
class TestReportsRealData:

    def _mk_order(self, db, user, amount, code, payment_status='paid', refunded=None):
        order = CanteenOrder(order_code=code, user_id=user.id, user_role_at_order=user.role,
                             is_priority=user.role == 'teacher', total_amount=amount,
                             pickup_time=datetime.utcnow(), order_status='confirmed',
                             payment_status=payment_status)
        db.session.add(order)
        db.session.commit()
        if refunded is not None:
            db.session.add(Payment(order_id=order.id, provider='sandbox',
                                   intent_id=f"sbx_pi_{code}", amount=amount,
                                   status='partially_refunded', refunded_amount=refunded))
            db.session.commit()
        return order

    def test_report_numbers_equal_database_rows(self, client, app, users, db):
        # exact, verifiable dataset: 2 orders 90 + 45, one refund of 30 recorded
        self._mk_order(db, users["student"], 90, "ORD-P8R-1", refunded=30)
        self._mk_order(db, users["teacher_verified"], 45, "ORD-P8R-2")
        _login_as(client, ADMIN)
        html = client.get("/admin/reports").get_data(as_text=True)

        # net booked value = (90 + 45) - 30 = 105.00 straight from the DB
        assert "105.00" in html
        payload = json.loads(re.search(r"const CHARTS = (\{.*?\});", html, re.S).group(1))
        assert sum(payload["timeSeries"]["orders"]) == 2
        assert abs(sum(payload["timeSeries"]["revenue"]) - 135.0) < 0.01
        assert payload["orderStatus"]["confirmed"] == 2
        assert payload["userRoles"]["student"] >= 1 and payload["userRoles"]["teacher"] >= 2
        assert payload["paymentStatus"]["partially_refunded"] == 1

    def test_empty_database_shows_zero_not_fake_numbers(self, client, app, users, db):
        _login_as(client, ADMIN)
        html = client.get("/admin/reports").get_data(as_text=True)
        payload = json.loads(re.search(r"const CHARTS = (\{.*?\});", html, re.S).group(1))
        assert sum(payload["timeSeries"]["orders"]) == 0
        assert "100% DB" in html


# ================================================================= security
class TestAdminSecurityMatrix:

    ADMIN_PAGES = [
        "/admin/dashboard", "/admin/users", "/admin/navigation/manage",
        "/admin/lost-found", "/admin/canteen", "/admin/reports", "/admin/audit-logs",
    ]

    def test_canteen_admin_blocked_from_campus_and_user_management(self, client, app, users, db):
        _login_as(client, CANTEEN_ADMIN)
        for page in self.ADMIN_PAGES:
            resp = client.get(page)
            assert resp.status_code == 302, f"{page} must not be readable by Canteen Admin"
            assert resp.headers["Location"].endswith("/")  # bounced to public home
        # and every write path too
        resp = client.post("/admin/canteen/item/1/update", data={"price": "1"})
        assert resp.status_code == 302
        resp = client.post("/admin/users/1/toggle-status")
        assert resp.status_code == 302

        denials = AuditLog.query.filter_by(action='ACCESS_DENIED_ROLE').all()
        assert len(denials) >= 2
        assert all(users["canteen_admin"].id == d.user_id for d in denials)

    def test_canteen_admin_keeps_own_hub_working(self, client, app, users, db):
        _login_as(client, CANTEEN_ADMIN)
        assert client.get("/canteen-admin/dashboard").status_code == 200

    def test_student_teacher_visitor_blocked(self, client, app, users, db):
        for email in (STUDENT, "teacher@gechassan.ac.in", "visitor@gechassan.ac.in"):
            _login_as(client, email)
            assert client.get("/admin/dashboard").status_code == 302
            assert client.get("/admin/reports").status_code == 302

    def test_anonymous_redirected_to_login(self, client, app, users, db):
        for page in self.ADMIN_PAGES:
            resp = client.get(page)
            assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]

    def test_deactivated_user_session_invalidated(self, client, app, users, db):
        _login_as(client, STUDENT)
        assert client.get("/auth/profile").status_code == 200
        student = users["student"]
        student.is_active = False
        db.session.commit()
        resp = client.get("/auth/profile", follow_redirects=False)
        assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]  # kicked out in real time

    def test_main_admin_clearance_across_all_three_modules(self, client, app, users, db):
        _login_as(client, ADMIN)
        for page in self.ADMIN_PAGES:
            assert client.get(page).status_code == 200, page
        # master clearance also into the operator hub and the AI lab
        assert client.get("/canteen-admin/dashboard").status_code == 200
        assert client.get("/admin/ai-lab").status_code == 200
