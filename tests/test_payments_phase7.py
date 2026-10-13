"""
PHASE 7 TEST SUITE - Payment & Refund Processing.

All tests run against the deterministic SANDBOX provider (test mode only -
NO REAL MONEY is ever moved). Covers the 11 mandated scenarios:
  successful payment, failed payment, duplicate webhook, cancelled order,
  unavailable food, full refund, partial refund, failed refund, delayed
  refund, order not delivered, payment-successful-but-confirmation-failed.
Plus: backend verification, webhook signature rejection, duplicate-payment
prevention, transaction references, reserve/release of stock, teacher-first
integration rules and refund authorisation tracking.
"""
import json
from datetime import date, datetime, timedelta

import pytest

import app.blueprints.canteen.routes as canteen_routes
import app.blueprints.canteen_admin.routes as canteen_admin_routes
import app.utils.payment_service as payment_service
from app.database import db
from app.models import (
    CanteenCategory, CanteenItem, CanteenOrder, CanteenPickupSlot,
    Notification, Payment, Refund, WebhookEvent, AuditLog, User,
)
from app.utils.payment_providers import SandboxProvider
from tests.conftest import login


# ------------------------------------------------------------------ helpers

def _seed_menu(db, stock=50, price=45.00):
    cat = CanteenCategory(name="Breakfast", display_order=1)
    db.session.add(cat)
    db.session.commit()
    item = CanteenItem(category_id=cat.id, name="Masala Dosa", description="Tasty dosa",
                       price=price, stock_quantity=stock, preparation_time_mins=10)
    db.session.add(item)
    db.session.commit()
    return item


def _make_slot(days_ahead=1, start="12:30", end="13:30", capacity=10):
    slot = CanteenPickupSlot(
        name="Lunch Break", slot_date=date.today() + timedelta(days=days_ahead),
        start_time=start, end_time=end, order_capacity=capacity, is_active=True,
    )
    db.session.add(slot)
    db.session.commit()
    return slot


def _checkout(client, monkeypatch, item, qty=1, slot=None, data=None):
    monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
    with client.session_transaction() as sess:
        sess["canteen_cart"] = {str(item.id): qty}
    form = dict(data or {})
    if slot is not None:
        form["slot_id"] = str(slot.id)
    return client.post("/canteen/checkout", data=form)


def _post_webhook(client, app, event):
    """Send a correctly HMAC-signed sandbox webhook."""
    body = json.dumps(event).encode()
    sig = SandboxProvider.sign_payload(body, app.config["PAYMENT_WEBHOOK_SECRET"])
    return client.post("/canteen/webhook/sandbox", data=body,
                       content_type="application/json",
                       headers={"X-Sandbox-Signature": sig})


def _login_as(client, email):
    """Switch the logged-in user cleanly (login while signed in is refused)."""
    client.get("/auth/logout")
    return login(client, email)


def _paid_order(client, app, monkeypatch, item, qty=2):
    """Checkout helper that leaves a PAID + CONFIRMED order (sandbox success)."""
    _login_as(client, "student@gechassan.ac.in")
    resp = _checkout(client, monkeypatch, item, qty=qty,
                     data={"payment_method": "upi_simulation"})
    assert resp.status_code == 302
    return CanteenOrder.query.order_by(CanteenOrder.id.desc()).one()


# ============================================================ 1. successful
class TestSuccessfulPayment:

    def test_checkout_captures_payment_and_reserves_stock(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=50)
        order = _paid_order(client, app, monkeypatch, item, qty=2)

        payment = Payment.query.filter_by(order_id=order.id).one()
        assert payment.status == 'succeeded'
        assert payment.provider == 'sandbox'
        assert payment.intent_id.startswith('sbx_pi_')
        # transaction reference recorded from the gateway, not from the browser
        assert payment.transaction_reference and payment.transaction_reference.startswith('sbx_ch_')
        assert float(payment.amount) == 90.0
        assert order.payment_status == 'paid'
        assert order.order_status == 'confirmed'
        # reservation: stock deducted exactly once for the paid order
        assert item.stock_quantity == 48
        # money state never leaves the backend: client secret is stored but the
        # webhook/verify path is what finalises async payments.
        assert payment.succeeded_at is not None

    def test_start_payment_is_idempotent_no_double_charge(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=50)
        order = _paid_order(client, app, monkeypatch, item, qty=1)
        first_intent = order.payment.intent_id
        # Re-invoking payment for an already-succeeded order is a no-op:
        payment, result = payment_service.start_payment(order)
        assert payment.id == order.payment.id
        assert payment.intent_id == first_intent
        assert result.status == 'succeeded'
        assert Payment.query.count() == 1

    def test_cash_at_counter_creates_no_gateway_payment(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=50)
        login(client, "student@gechassan.ac.in")
        _checkout(client, monkeypatch, item, qty=1, data={"payment_method": "cash_at_counter"})
        order = CanteenOrder.query.one()
        assert order.payment_status == 'pending'
        assert order.order_status == 'confirmed'
        assert order.payment is None


# ================================================================= 2. failed
class TestFailedPayment:

    def test_declined_payment_charges_nothing_and_releases_stock(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=50)
        app.config['PAYMENT_SANDBOX_PAYMENT_OUTCOME'] = 'failed'
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, qty=3, data={"payment_method": "upi_simulation"})

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/canteen/cart")
        order = CanteenOrder.query.order_by(CanteenOrder.id.desc()).one()
        assert order.order_status == 'cancelled'
        assert order.payment_status == 'pending'
        payment = order.payment
        assert payment.status == 'failed'
        assert 'declined' in (payment.failure_reason or '').lower()
        # the reservation was fully released - no phantom stock loss
        assert item.stock_quantity == 50
        # customer is told, never silently dropped
        assert Notification.query.filter_by(user_id=order.user_id).count() >= 1


# =============================================================== 3. webhook
class TestWebhookProcessing:

    def test_unsigned_webhook_is_rejected(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        app.config['PAYMENT_SANDBOX_PAYMENT_OUTCOME'] = 'processing'
        order = _paid_order(client, app, monkeypatch, item, qty=1)
        resp = client.post("/canteen/webhook/sandbox",
                           data=json.dumps({"id": "evt_x", "type": "payment_intent.succeeded",
                                            "data": {"intent_id": order.payment.intent_id}}),
                           content_type="application/json")
        assert resp.status_code == 400
        assert order.payment.status == 'processing'  # state unchanged by unsigned payload
        assert WebhookEvent.query.count() == 0

    def test_signed_success_webhook_confirms_order(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        app.config['PAYMENT_SANDBOX_PAYMENT_OUTCOME'] = 'processing'
        monkeypatch.setattr(payment_service, "generate_order_qr", lambda order, save_to_disk=True: None)
        order = _paid_order(client, app, monkeypatch, item, qty=1)
        assert order.order_status == 'pending'          # not confirmed on browser claim
        assert order.payment.status == 'processing'

        resp = _post_webhook(client, app, {
            "id": "evt_success_1", "type": "payment_intent.succeeded",
            "data": {"intent_id": order.payment.intent_id, "reference": "sbx_ch_verified"},
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'processed'
        db.session.refresh(order); db.session.refresh(order.payment)
        assert order.payment.status == 'succeeded'
        assert order.payment.transaction_reference == 'sbx_ch_verified'
        assert order.payment_status == 'paid'
        assert order.order_status == 'confirmed'

    def test_duplicate_webhook_processed_exactly_once(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        app.config['PAYMENT_SANDBOX_PAYMENT_OUTCOME'] = 'processing'
        monkeypatch.setattr(payment_service, "generate_order_qr", lambda order, save_to_disk=True: None)
        order = _paid_order(client, app, monkeypatch, item, qty=1)
        event = {"id": "evt_dup_1", "type": "payment_intent.succeeded",
                 "data": {"intent_id": order.payment.intent_id, "reference": "sbx_ch_1"}}

        assert _post_webhook(client, app, event).get_json()['status'] == 'processed'
        # gateway resends the SAME event id - must be refused before any logic
        assert _post_webhook(client, app, event).get_json()['status'] == 'duplicate'
        assert WebhookEvent.query.filter_by(event_id="evt_dup_1").count() == 1
        # confirmation notification exists exactly once
        confirmed = Notification.query.filter(
            Notification.dedup_key == f"canteen:{order.id}:confirmed").count()
        assert confirmed == 1

    def test_failure_webhook_cancels_and_releases(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=30)
        app.config['PAYMENT_SANDBOX_PAYMENT_OUTCOME'] = 'processing'
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        assert item.stock_quantity == 28

        resp = _post_webhook(client, app, {
            "id": "evt_fail_1", "type": "payment_intent.payment_failed",
            "data": {"intent_id": order.payment.intent_id, "failure_reason": "card declined"},
        })
        assert resp.get_json()['status'] == 'processed'
        db.session.refresh(order)
        assert order.payment.status == 'failed'
        assert order.order_status == 'cancelled'
        assert item.stock_quantity == 30                    # reservation released

    def test_unknown_provider_slug_rejected(self, client, app, users, db):
        resp = client.post("/canteen/webhook/stripe", data=b"{}", content_type="application/json")
        assert resp.status_code == 404


# ============================================================ 4. cancellation
class TestCancelledOrder:

    def test_customer_cancel_refunds_through_gateway(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=40)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        assert item.stock_quantity == 38

        login(client, "student@gechassan.ac.in")
        resp = client.post(f"/canteen/order/{order.id}/cancel",
                           data={"refund_reason": "Plans changed"})
        assert resp.status_code == 302
        db.session.refresh(order)
        assert order.order_status == 'cancelled'
        assert order.payment_status == 'refunded'
        assert item.stock_quantity == 40                    # stock released

        refund = Refund.query.filter_by(order_id=order.id).one()
        assert refund.status == 'succeeded'
        assert refund.provider_refund_id.startswith('sbx_re_')   # gateway ref tracked
        assert not refund.is_partial
        assert float(refund.amount) == 90.0
        assert order.payment.status == 'refunded'
        assert float(order.payment.refunded_amount) == 90.0


# ========================================================== 5. unfulfillable
class TestUnavailableFood:

    def test_unavailable_item_never_charged(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        item.is_available = False
        db.session.commit()
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, qty=1, data={"payment_method": "upi_simulation"})
        assert resp.headers["Location"].endswith("/canteen/cart")
        assert CanteenOrder.query.count() == 0
        assert Payment.query.count() == 0                   # nothing charged

    def test_insufficient_stock_never_charged(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=1)
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, qty=5, data={"payment_method": "upi_simulation"})
        assert resp.headers["Location"].endswith("/canteen/cart")
        assert Payment.query.count() == 0
        assert item.stock_quantity == 1                     # untouched

    def test_teacher_reserved_slot_blocks_student_before_payment(self, client, app, users, db, monkeypatch):
        # Teacher-first never silently cancels paid student orders: students are
        # refused BEFORE any charge while reserved seats remain.
        item = _seed_menu(db)
        app.config['CANTEEN_TEACHER_RESERVE_RATIO'] = 1.0
        slot = _make_slot(capacity=2)
        login(client, "student@gechassan.ac.in")
        resp = _checkout(client, monkeypatch, item, qty=1, slot=slot,
                         data={"payment_method": "upi_simulation"})
        assert resp.headers["Location"].endswith("/canteen/cart")
        assert CanteenOrder.query.count() == 0
        assert Payment.query.count() == 0


# ============================================================== 6. full refund
class TestFullRefund:

    def test_complaint_to_authorised_gateway_refund(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)

        # step 1: customer complaint recorded
        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "Duplicated my order by mistake"})
        db.session.refresh(order)
        assert order.order_status == 'refund_requested'
        complaint = Refund.query.filter_by(order_id=order.id, status='requested').one()
        assert 'Duplicated' in complaint.complaint_note

        # steps 2-8: canteen admin verifies, authorises, initiates via gateway
        _login_as(client, "canteen@gechassan.ac.in")
        resp = client.post(f"/canteen-admin/orders/{order.id}/refund",
                           data={"refund_reason": "Confirmed duplicate order"})
        assert resp.status_code == 302
        db.session.refresh(order); db.session.refresh(complaint); db.session.refresh(order.payment)
        assert complaint.status == 'succeeded'              # only on reliable confirmation
        assert complaint.provider_refund_id.startswith('sbx_re_')
        assert complaint.authorized_by == users["canteen_admin"].id
        assert complaint.authorized_at is not None and complaint.confirmed_at is not None
        assert not complaint.is_partial
        assert order.order_status == 'refunded'
        assert order.payment_status == 'refunded'
        assert order.payment.status == 'refunded'
        # step 8: user notified about the settled refund
        assert Notification.query.filter(
            Notification.title == "Refund completed").count() == 1
        assert AuditLog.query.filter_by(action='CANTEEN_REFUND_INITIATED').count() == 1


# ========================================================== 7. partial refund
class TestPartialRefund:

    def test_partial_refund_tracks_remaining_balance(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)   # ₹90 paid

        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "One dosa missing from the bag"})
        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund",
                    data={"amount": "30.00", "refund_reason": "One item not delivered"})

        refund = Refund.query.filter_by(order_id=order.id).one()
        db.session.refresh(order.payment)
        assert refund.is_partial is True
        assert float(refund.amount) == 30.0
        assert refund.status == 'succeeded'
        assert order.payment.status == 'partially_refunded'
        assert float(order.payment.refunded_amount) == 30.0
        assert abs(order.payment.refundable_amount - 60.0) < 0.005
        assert order.payment_status == 'partially_refunded'

    def test_over_refund_refused(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund",
                    data={"amount": "99999.00", "refund_reason": "greedy"})
        assert Refund.query.filter_by(order_id=order.id).count() == 0
        db.session.refresh(order.payment)
        assert order.payment.status == 'succeeded'          # untouched


# =========================================================== 8. failed refund
class TestFailedRefund:

    def test_failed_refund_stays_visible_and_retriable(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "Not delivered"})
        app.config['PAYMENT_SANDBOX_REFUND_OUTCOME'] = 'failed'

        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund", data={})
        refund = Refund.query.filter_by(order_id=order.id).one()
        assert refund.status == 'failed'
        assert refund.attempts == 1
        db.session.refresh(order.payment)
        assert order.payment.status == 'succeeded'          # money NOT marked returned
        assert order.payment_status == 'paid'
        assert Notification.query.filter_by(title="Refund attempt failed").count() == 1

        # gateway recovers - admin retries the SAME refund record
        app.config['PAYMENT_SANDBOX_REFUND_OUTCOME'] = 'succeeded'
        client.post(f"/canteen-admin/refunds/{refund.id}/retry")
        db.session.refresh(refund); db.session.refresh(order.payment)
        assert refund.status == 'succeeded'
        assert refund.attempts == 2
        assert order.payment.status == 'refunded'


# ========================================================== 9. delayed refund
class TestDelayedRefund:

    def test_processing_refund_only_completes_on_confirmation(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "Waited too long, gave up"})
        app.config['PAYMENT_SANDBOX_REFUND_OUTCOME'] = 'processing'

        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund", data={})
        refund = Refund.query.filter_by(order_id=order.id).one()
        db.session.refresh(order); db.session.refresh(order.payment)
        assert refund.status == 'processing'
        assert refund.provider_refund_id                      # gateway ref tracked
        assert order.order_status == 'refund_processing'      # NOT silently 'refunded'
        assert order.payment.status == 'succeeded'            # money not yet returned

        # settlement is confirmed later by a signed refund webhook
        resp = _post_webhook(client, app, {
            "id": "evt_refund_settled", "type": "charge.refund.updated",
            "data": {"provider_refund_id": refund.provider_refund_id, "status": "succeeded"},
        })
        assert resp.get_json()['status'] == 'processed'
        db.session.refresh(refund); db.session.refresh(order)
        assert refund.status == 'succeeded'
        assert refund.confirmed_at is not None
        assert order.order_status == 'refunded'
        assert order.payment_status == 'refunded'

    def test_resync_route_settles_pending_refund(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=1)
        app.config['PAYMENT_SANDBOX_REFUND_OUTCOME'] = 'processing'
        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund", data={})
        refund = Refund.query.filter_by(order_id=order.id).one()
        assert refund.status == 'processing'

        app.config['PAYMENT_SANDBOX_REFUND_OUTCOME'] = 'succeeded'   # not used by re-sync
        client.post(f"/canteen-admin/refunds/{refund.id}/retry")
        db.session.refresh(refund)
        assert refund.status == 'succeeded'        # settled via provider verify_refund


# ====================================================== 10. not delivered
class TestOrderNotDelivered:

    def test_admin_marks_refunded_via_gateway_not_status_flip(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        client.post(f"/canteen/order/{order.id}/request-refund",
                    data={"refund_reason": "Order was never handed over at the counter"})

        _login_as(client, "canteen@gechassan.ac.in")
        resp = client.post(f"/canteen-admin/orders/{order.id}/status",
                           data={"new_status": "refunded"})
        assert resp.status_code == 302
        db.session.refresh(order)
        assert order.order_status == 'refunded'
        assert order.payment_status == 'refunded'
        refund = Refund.query.filter_by(order_id=order.id).one()
        assert refund.status == 'succeeded'
        assert refund.authorized_by == users["canteen_admin"].id
        assert refund.provider_refund_id
        # the money movement went through the gateway exactly once
        assert refund.attempts == 1

    def test_paid_student_order_never_silently_cancelled(self, client, app, users, db, monkeypatch):
        # Admin cancellation of a captured online order always produces a
        # gateway refund record + customer notification - nothing silent.
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=2)
        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/status",
                    data={"new_status": "cancelled", "refund_reason": "Kitchen closed"})
        db.session.refresh(order)
        assert order.order_status == 'cancelled'
        assert order.payment_status == 'refunded'
        assert Refund.query.filter_by(order_id=order.id, status='succeeded').count() == 1
        assert Notification.query.filter(
            Notification.user_id == order.user_id,
            Notification.title.in_(["Order cancelled", "Refund completed"])).count() >= 1


# ==================================== 11. paid but confirmation failed
class TestPaymentSuccessConfirmationFailure:

    def test_mismatch_flagged_then_admin_resolves(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db, stock=40)
        monkeypatch.setattr(canteen_routes, "generate_order_qr",
                            lambda order, save_to_disk=True: (_ for _ in ()).throw(RuntimeError("QR service down")))
        login(client, "student@gechassan.ac.in")
        with client.session_transaction() as sess:
            sess["canteen_cart"] = {str(item.id): 1}
        resp = client.post("/canteen/checkout", data={"payment_method": "upi_simulation"})
        assert resp.status_code == 302

        order = CanteenOrder.query.one()
        db.session.refresh(order)
        payment = order.payment
        assert payment.status == 'succeeded'          # money really captured
        assert payment.confirm_mismatch is True       # ... and the mismatch is recorded
        assert order.order_status == 'pending'        # NOT half-confirmed
        assert item.stock_quantity == 39              # reservation still held
        assert AuditLog.query.filter_by(action='PAYMENT_CONFIRM_MISMATCH').count() == 1

        # admin resolves: confirmation retry succeeds this time
        monkeypatch.setattr(payment_service, "generate_order_qr", lambda order, save_to_disk=True: None)
        _login_as(client, "canteen@gechassan.ac.in")
        resp = client.post(f"/canteen-admin/orders/{order.id}/resolve-mismatch")
        assert resp.status_code == 302
        db.session.refresh(order); db.session.refresh(payment)
        assert payment.confirm_mismatch is False
        assert order.order_status == 'confirmed'
        assert AuditLog.query.filter_by(action='PAYMENT_MISMATCH_RESOLVED').count() == 1

    def test_mismatched_payment_can_be_refunded_instead(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        monkeypatch.setattr(canteen_routes, "generate_order_qr",
                            lambda order, save_to_disk=True: (_ for _ in ()).throw(RuntimeError("still down")))
        login(client, "student@gechassan.ac.in")
        with client.session_transaction() as sess:
            sess["canteen_cart"] = {str(item.id): 1}
        client.post("/canteen/checkout", data={"payment_method": "upi_simulation"})
        order = CanteenOrder.query.one()

        _login_as(client, "canteen@gechassan.ac.in")
        client.post(f"/canteen-admin/orders/{order.id}/refund",
                    data={"refund_reason": "Cannot prepare; returning money"})
        db.session.refresh(order); db.session.refresh(order.payment)
        assert order.payment.status == 'refunded'
        assert order.payment_status == 'refunded'


# ================================================= RBAC on money endpoints
class TestPaymentAdminRbac:

    def test_student_cannot_use_refund_console(self, client, app, users, db, monkeypatch):
        item = _seed_menu(db)
        order = _paid_order(client, app, monkeypatch, item, qty=1)   # logs in as student
        resp = client.post(f"/canteen-admin/orders/{order.id}/refund", data={})
        assert resp.status_code in (302, 403)
        db.session.refresh(order.payment)
        assert order.payment.status == 'succeeded'                   # no refund happened

    def test_refund_requires_canteen_admin_role(self, client, app, users, db):
        login(client, "visitor@gechassan.ac.in")
        resp = client.post("/canteen-admin/orders/1/refund", data={})
        assert resp.status_code in (302, 403)
