"""
PHASE 6 TEST SUITE - Smart Canteen Booking.

Covers: pickup slot configuration, capacity-aware checkout with configurable
teacher-first allocation, the 9-state order lifecycle (incl. refunds),
tokenized privacy-safe QR pickup verification with double-redemption refusal,
canteen notifications (dedup-safe), menu management with photo uploads,
RBAC, and the canteen operations report.
"""
import io
from datetime import date, datetime, timedelta

import pytest

import app.blueprints.canteen.routes as canteen_routes
import app.blueprints.canteen_admin.routes as canteen_admin_routes
from app.models import (
    CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem,
    CanteenPickupSlot, Notification, User,
)
from app.utils.qr_generator import pickup_qr_payload, parse_pickup_payload
from app.utils import canteen_booking as booking
from tests.conftest import login


# ------------------------------------------------------------------ helpers

def _seed_menu(db, stock=50, prep=10):
    cat = CanteenCategory(name="Breakfast", display_order=1)
    db.session.add(cat)
    db.session.commit()
    item = CanteenItem(category_id=cat.id, name="Masala Dosa", description="Tasty dosa",
                       price=45.00, stock_quantity=stock, preparation_time_mins=prep)
    db.session.add(item)
    db.session.commit()
    return item


def _make_slot(days_ahead=1, start="12:30", end="13:30", capacity=10, name="Lunch Break"):
    slot = CanteenPickupSlot(
        name=name, slot_date=date.today() + timedelta(days=days_ahead),
        start_time=start, end_time=end, order_capacity=capacity, is_active=True,
    )
    from app.database import db
    db.session.add(slot)
    db.session.commit()
    return slot


def _cfg(app):
    return {
        'CANTEEN_TEACHER_PRIORITY_ENABLED': app.config['CANTEEN_TEACHER_PRIORITY_ENABLED'],
        'CANTEEN_TEACHER_RESERVE_RATIO': app.config['CANTEEN_TEACHER_RESERVE_RATIO'],
        'CANTEEN_AUTO_CONFIRM': app.config['CANTEEN_AUTO_CONFIRM'],
        'CANTEEN_MIN_LEAD_MINS': app.config['CANTEEN_MIN_LEAD_MINS'],
        'CANTEEN_PREP_MIN_PER_ORDER': app.config['CANTEEN_PREP_MIN_PER_ORDER'],
    }


def _checkout(client, monkeypatch, item, qty=1, slot=None, data=None):
    monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
    with client.session_transaction() as sess:
        sess["canteen_cart"] = {str(item.id): qty}
    form = dict(data or {})
    if slot is not None:
        form["slot_id"] = str(slot.id)
    return client.post("/canteen/checkout", data=form)


def _png_bytes(seed=7):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(96, 96, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (76, 76), (0, 0, 255), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


_ORDER_SEQ = iter(range(1, 100000))

def _order(email, **kwargs):
    user = User.query.filter_by(email=email).first()
    order = CanteenOrder(user_id=user.id, user_role_at_order=user.role,
                         total_amount=kwargs.pop('total', 90.0),
                         pickup_time=datetime.now() + timedelta(hours=1),
                         order_status=kwargs.pop('status', 'confirmed'),
                         order_code=kwargs.pop('code', f"ORD-T-{next(_ORDER_SEQ)}"),
                         **kwargs)
    from app.database import db
    db.session.add(order)
    db.session.commit()
    return order


# ================================================================ slot admin

class TestPickupSlotConfiguration:

    def test_canteen_admin_creates_slot(self, client, users, db):
        login(client, "canteen@gechassan.ac.in")
        resp = client.post("/canteen-admin/slots", data={
            "name": "Evening Tea", "slot_date": (date.today() + timedelta(days=1)).isoformat(),
            "start_time": "16:00", "end_time": "16:45", "order_capacity": "25",
        })
        assert resp.status_code == 302
        slot = CanteenPickupSlot.query.filter_by(name="Evening Tea").first()
        assert slot is not None and slot.order_capacity == 25

    def test_slot_end_before_start_rejected(self, client, users, db):
        login(client, "canteen@gechassan.ac.in")
        client.post("/canteen-admin/slots", data={
            "name": "Bad Slot", "slot_date": (date.today() + timedelta(days=1)).isoformat(),
            "start_time": "15:00", "end_time": "14:00", "order_capacity": "10",
        })
        assert CanteenPickupSlot.query.filter_by(name="Bad Slot").first() is None

    def test_slot_toggle_closes_and_reopens(self, client, users, db):
        slot = _make_slot()
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/slots/{slot.id}/toggle")
        assert slot.is_active is False
        client.post(f"/canteen-admin/slots/{slot.id}/toggle")
        assert slot.is_active is True

    def test_cart_lists_bookable_slots_with_capacity(self, client, users, db):
        item = _seed_menu(db)
        slot = _make_slot(capacity=7)
        login(client, "student@gechassan.ac.in")
        with client.session_transaction() as sess:
            sess["canteen_cart"] = {str(item.id): 1}
        body = client.get("/canteen/cart").get_data(as_text=True)
        # capacity 7 minus the 2-seat teacher reservation (ceil(7*0.25)) for students
        assert slot.name in body and "5 seats left" in body

    def test_student_blocked_from_slot_admin(self, client, users):
        login(client, "student@gechassan.ac.in")
        assert client.get("/canteen-admin/slots").status_code == 302
        assert client.get("/canteen-admin/reports").status_code == 302


# ================================================================ checkout

class TestSlotAwareCheckout:

    def test_checkout_confirms_books_slot_and_notifies(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        slot = _make_slot(capacity=5)
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, qty=2, slot=slot,
                         data={"payment_method": "upi_simulation"})
        assert resp.status_code == 302
        order = CanteenOrder.query.order_by(CanteenOrder.id.desc()).first()
        assert order.order_status == 'confirmed'
        assert order.slot_id == slot.id
        assert order.pickup_time == slot.starts_at
        assert order.confirmed_at is not None
        assert order.pickup_token and len(order.pickup_token) >= 20
        assert order.estimated_ready_at is not None
        assert order.estimated_ready_at >= slot.starts_at
        assert item.stock_quantity == 48
        notes = Notification.query.filter_by(user_id=order.user_id, category='canteen').all()
        assert len(notes) == 1 and notes[0].dedup_key == f"canteen:{order.id}:confirmed"

    def test_insufficient_stock_creates_nothing(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=3)
        slot = _make_slot()
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, qty=5, slot=slot)
        assert CanteenOrder.query.count() == 0
        assert item.stock_quantity == 3  # untouched

    def test_full_slot_rejected_with_reason_and_alternative(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=100)
        app.config['CANTEEN_TEACHER_PRIORITY_ENABLED'] = False
        slot = _make_slot(capacity=1)
        alt = _make_slot(capacity=9, name="Evening Tea")
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)          # fills it
        resp = _checkout(client, monkeypatch, item, slot=slot)   # second attempt
        assert CanteenOrder.query.count() == 1
        body = client.get("/canteen/cart").get_data(as_text=True)
        assert alt.name in body  # alternative slot still offered

    def test_legacy_free_datetime_when_no_slots(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, slot=None,
                         data={"pickup_time": (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')})
        assert resp.status_code == 302
        order = CanteenOrder.query.one()
        assert order.slot_id is None and order.order_status == 'confirmed'

    def test_manual_confirm_flow_when_auto_confirm_disabled(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        slot = _make_slot()
        app.config['CANTEEN_AUTO_CONFIRM'] = False
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        order = CanteenOrder.query.one()
        assert order.order_status == 'pending' and order.pickup_token is None

        client.get("/auth/logout")
        login(client, "canteen@gechassan.ac.in")
        monkeypatch.setattr(canteen_admin_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "confirmed"})
        assert order.order_status == 'confirmed'
        assert order.pickup_token and order.confirmed_at is not None


# ======================================================= teacher priority

class TestTeacherFirstAllocation:

    def test_reserve_ratio_blocks_students_but_not_teachers(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=200)
        app.config['CANTEEN_TEACHER_RESERVE_RATIO'] = 0.5
        slot = _make_slot(capacity=4)   # reserve = 2
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        _checkout(client, monkeypatch, item, slot=slot)   # students fill 2 of 4
        # third student hits the teacher reservation
        client.get("/auth/logout")
        login(client, "visitor@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        assert CanteenOrder.query.count() == 2
        # verified teacher still gets a reserved seat
        client.get("/auth/logout")
        login(client, "teacher@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        order = CanteenOrder.query.order_by(CanteenOrder.id.desc()).first()
        assert order.is_priority is True
        assert CanteenOrder.query.count() == 3

    def test_unverified_teacher_gets_no_reserved_seats(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=200)
        app.config['CANTEEN_TEACHER_RESERVE_RATIO'] = 0.5
        slot = _make_slot(capacity=4)
        login(client, "pending.teacher@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        order = CanteenOrder.query.one()
        assert order.is_priority is False
        # treated as a student: remaining students can be blocked by reservation
        cfg = _cfg(app)
        info = booking.slot_availability(slot, cfg, is_priority=False)
        assert info['remaining_for_me'] == 1  # capacity 4 - 1 booked - 2 teacher-reserved

    def test_priority_disabled_means_first_come(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=200)
        app.config['CANTEEN_TEACHER_PRIORITY_ENABLED'] = False
        slot = _make_slot(capacity=2)
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, slot=slot)
        _checkout(client, monkeypatch, item, slot=slot)
        assert CanteenOrder.query.count() == 2
        cfg = _cfg(app)
        assert booking.slot_availability(slot, cfg, False)['allowed'] is False

    def test_reservation_releases_when_slot_opens(self, db, app, users):
        slot = _make_slot(days_ahead=0, start="00:00", end="23:59")
        # Slot opened long ago (starts 00:00): reserved seats must be released
        cfg = _cfg(app)
        info = booking.slot_availability(slot, cfg, is_priority=False)
        assert info['teacher_reserved'] == 0
        assert info['remaining_for_me'] == slot.order_capacity


# ====================================================== lifecycle + refunds

class TestOrderLifecycle:

    def test_illegal_transition_refused(self, client, app, users, db):
        order2 = _order("student@gechassan.ac.in", status='collected', code="ORD-COL-1")
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order2.id}/status", data={"new_status": "preparing"})
        assert order2.order_status == 'collected'

    def test_full_happy_path_to_ready(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='confirmed')
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "preparing"})
        assert order.order_status == 'preparing'
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "ready"})
        assert order.order_status == 'ready'
        notes = Notification.query.filter_by(user_id=order.user_id).all()
        assert {n.dedup_key for n in notes} == {f"canteen:{order.id}:preparing", f"canteen:{order.id}:ready"}

    def test_customer_refund_request_and_admin_processing(self, client, app, users, db):
        item = _seed_menu(db, stock=20)
        order = _order("student@gechassan.ac.in", status='preparing')
        db.session.add(CanteenOrderItem(order_id=order.id, item_id=item.id, item_name=item.name,
                                        unit_price=item.price, quantity=1, subtotal=item.price))
        db.session.commit()

        login(client, "student@gechassan.ac.in")
        client.post(f"/canteen/order/{order.id}/request-refund", data={"refund_reason": "Class trip"})
        assert order.order_status == 'refund_requested'
        assert order.refund_reason == "Class trip"

        client.get("/auth/logout")
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "refund_processing"})
        assert order.order_status == 'refund_processing'
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "refunded"})
        assert order.order_status == 'refunded'
        assert order.payment_status == 'refunded'
        # cooked food never returns to stock
        assert item.stock_quantity == 20

    def test_refund_notifications_are_deduped(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='refund_requested')
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "refund_processing"})
        # replay the same transition - now illegal, must not add a second alert
        client.post(f"/canteen-admin/orders/{order.id}/status", data={"new_status": "refund_processing"})
        notes = Notification.query.filter_by(dedup_key=f"canteen:{order.id}:refund_processing").count()
        assert notes == 1

    def test_cancel_confirmed_order_restores_stock(self, client, app, users, db):
        item = _seed_menu(db, stock=20)
        order = _order("student@gechassan.ac.in", status='confirmed')
        db.session.add(CanteenOrderItem(order_id=order.id, item_id=item.id, item_name=item.name,
                                        unit_price=item.price, quantity=3, subtotal=3 * item.price))
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        client.post(f"/canteen/order/{order.id}/cancel", data={})
        assert order.order_status == 'cancelled'
        assert item.stock_quantity == 23


# ============================================================== QR pickup

class TestTokenizedQRPickup:

    def test_payload_contains_no_personal_information(self, db, users):
        order = _order("student@gechassan.ac.in", status='confirmed')
        order.pickup_token = "tok_ABC123"
        payload = pickup_qr_payload(order)
        assert payload == f"SC360-PICKUP:{order.order_code}:tok_ABC123"
        customer = order.customer
        for secret in (customer.email, customer.full_name, str(order.user_id), "student"):
            assert secret not in payload

    def test_payload_roundtrip(self):
        code, token = parse_pickup_payload("SC360-PICKUP:ORD-9:tok_X")
        assert code == "ORD-9" and token == "tok_X"
        code, token = parse_pickup_payload("ord-2026-42")   # manual entry
        assert code == "ORD-2026-42" and token is None

    def test_scan_verify_collects_once(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='ready')
        order.pickup_token = "tok_UNIQUE"
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        resp = client.post("/canteen-admin/verify-pickup",
                           data={"order_code": f"SC360-PICKUP:{order.order_code}:tok_UNIQUE"})
        assert order.order_status == 'collected' and order.collected_at is not None
        # second redemption of the same QR is refused
        first_collected_at = order.collected_at
        client.post("/canteen-admin/verify-pickup",
                    data={"order_code": f"SC360-PICKUP:{order.order_code}:tok_UNIQUE"})
        assert order.collected_at == first_collected_at
        assert order.order_status == 'collected'

    def test_wrong_token_refused(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='ready')
        order.pickup_token = "tok_RIGHT"
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        client.post("/canteen-admin/verify-pickup",
                    data={"order_code": f"SC360-PICKUP:{order.order_code}:tok_WRONG"})
        assert order.order_status == 'ready'

    def test_manual_code_cannot_redeem_tokenized_order(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='ready')
        order.pickup_token = "tok_SECRET"
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        client.post("/canteen-admin/verify-pickup", data={"order_code": order.order_code})
        assert order.order_status == 'ready'

    def test_legacy_order_without_token_still_works(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='ready', code="ORD-LEGACY-1")
        assert order.pickup_token is None
        login(client, "canteen@gechassan.ac.in")
        client.post("/canteen-admin/verify-pickup", data={"order_code": order.order_code})
        assert order.order_status == 'collected'

    def test_cancelled_order_cannot_be_redeemed(self, client, app, users, db):
        order = _order("student@gechassan.ac.in", status='cancelled', code="ORD-CANC-1")
        order.pickup_token = "tok_C"
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        client.post("/canteen-admin/verify-pickup",
                    data={"order_code": f"SC360-PICKUP:{order.order_code}:tok_C"})
        assert order.order_status == 'cancelled'


# ==================================================== menu management

class TestMenuManagement:

    def test_add_item_with_photo(self, client, users, db):
        cat = CanteenCategory(name="Beverages")
        db.session.add(cat)
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        data = {
            "action": "add_item", "name": "Filter Coffee", "category_id": str(cat.id),
            "price": "25", "stock_quantity": "40", "preparation_time_mins": "5",
            "description": "Fresh filter coffee",
        }
        data['photo'] = (io.BytesIO(_png_bytes(1)), "coffee.png")
        client.post("/canteen-admin/menu", data=data, content_type="multipart/form-data")
        item = CanteenItem.query.filter_by(name="Filter Coffee").first()
        assert item is not None
        assert item.photo_url and item.photo_url.startswith("/static/uploads/canteen/")
        assert item.preparation_time_mins == 5

    def test_invalid_photo_rejected_and_item_not_created(self, client, users, db):
        cat = CanteenCategory(name="Snacks")
        db.session.add(cat)
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        data = {
            "action": "add_item", "name": "Fake Item", "category_id": str(cat.id),
            "price": "10", "stock_quantity": "5",
            "photo": (io.BytesIO(b"this is definitely not an image"), "fake.png"),
        }
        client.post("/canteen-admin/menu", data=data, content_type="multipart/form-data")
        assert CanteenItem.query.filter_by(name="Fake Item").first() is None

    def test_edit_price_stock_name(self, client, users, db):
        item = _seed_menu(db, stock=10)
        login(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/menu/edit/{item.id}", data={
            "name": "Ghee Masala Dosa", "price": "60", "stock_quantity": "25",
            "preparation_time_mins": "12", "description": item.description,
            "category_id": str(item.category_id), "is_available": "1",
        })
        assert item.name == "Ghee Masala Dosa"
        assert float(item.price) == 60.0
        assert item.stock_quantity == 25
        assert item.preparation_time_mins == 12

    def test_student_cannot_edit_menu(self, client, users, db):
        item = _seed_menu(db)
        login(client, "student@gechassan.ac.in")
        resp = client.post(f"/canteen-admin/menu/edit/{item.id}", data={"price": "1"})
        assert resp.status_code == 302
        assert float(item.price) == 45.0


# ==================================================== cart & menu UX

class TestCartAndMenuUX:

    def test_menu_search_filters_items(self, client, db):
        _seed_menu(db)
        body = client.get("/canteen/?q=dosa").get_data(as_text=True)
        assert "Masala Dosa" in body
        body2 = client.get("/canteen/?q=zzz-missing").get_data(as_text=True)
        assert "Masala Dosa" not in body2
        assert "No dishes match your search" in body2

    def test_cart_quantity_update_and_removal(self, client, users, db):
        item = _seed_menu(db, stock=10)
        login(client, "student@gechassan.ac.in")
        with client.session_transaction() as sess:
            sess["canteen_cart"] = {str(item.id): 2}
        client.post("/canteen/cart/update", data={"item_id": str(item.id), "quantity": "4"})
        with client.session_transaction() as sess:
            assert sess["canteen_cart"][str(item.id)] == 4
        # capped at live stock
        client.post("/canteen/cart/update", data={"item_id": str(item.id), "quantity": "999"})
        with client.session_transaction() as sess:
            assert sess["canteen_cart"][str(item.id)] == 10
        # zero removes the line
        client.post("/canteen/cart/update", data={"item_id": str(item.id), "quantity": "0"})
        with client.session_transaction() as sess:
            assert str(item.id) not in sess.get("canteen_cart", {})

    def test_order_page_shows_slot_and_estimate(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        slot = _make_slot(capacity=5)
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, slot=slot)
        order = CanteenOrder.query.one()
        body = client.get(f"/canteen/order/{order.order_code}").get_data(as_text=True)
        assert slot.name in body
        assert "Estimated Ready" in body


# ====================================================== reports

class TestCanteenReports:

    def test_report_aggregates(self, client, users, db):
        item = _seed_menu(db)
        order = _order("student@gechassan.ac.in", status='collected', code="ORD-REP-1")
        db.session.add(CanteenOrderItem(order_id=order.id, item_id=item.id, item_name=item.name,
                                        unit_price=item.price, quantity=2, subtotal=90))
        db.session.commit()
        login(client, "canteen@gechassan.ac.in")
        body = client.get("/canteen-admin/reports").get_data(as_text=True)
        assert "Canteen Operations Report" in body
        assert item.name in body          # top items table
        assert "Ready for Pickup" in body  # lifecycle mix labels
        assert "Revenue" in body
