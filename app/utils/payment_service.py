"""
PHASE 7 - Payment & refund orchestration shared by the customer checkout,
the canteen admin console and the webhook receiver.

Inventory semantics (reserve / release):
 - Stock is deducted when the order is created (the reservation).
 - A failed or abandoned payment RELEASES the reservation (stock restored,
   order visibly cancelled - the customer is told, never silently dropped).
 - A succeeded payment KEEPS the reservation; the order then proceeds through
   the normal Phase 6 lifecycle.

Money semantics:
 - Payment status changes ONLY from backend verification (provider confirm
   call or signature-verified webhook), never from browser input.
 - A captured payment whose order cannot be confirmed is flagged
   (Payment.confirm_mismatch) for admin action / auto-refund - money is
   never left unaccounted for.
 - Refunds become 'succeeded' only on reliable gateway confirmation.
"""
import json
import secrets
from datetime import datetime

from flask import current_app, url_for
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models import CanteenOrder, CanteenItem, Notification, AuditLog, Payment, Refund, WebhookEvent
from app.utils import canteen_booking as booking
from app.utils.payment_providers import get_provider
from app.utils.qr_generator import generate_order_qr


# ------------------------------------------------------------------ payments

def start_payment(order):
    """
    Create the gateway intent for an order and verify it backend-side.
    Returns (payment, IntentResult). Re-invoking for an already-succeeded
    payment is a no-op (duplicate payment prevention).
    """
    provider = get_provider()
    payment = Payment.query.filter_by(order_id=order.id).first()
    if payment and payment.status == 'succeeded':
        from app.utils.payment_providers import IntentResult
        return payment, IntentResult(status='succeeded', intent_id=payment.intent_id,
                                     reference=payment.transaction_reference or '')

    if not payment:
        payment = Payment(order_id=order.id, provider=provider.name,
                          amount=order.total_amount,
                          currency=current_app.config['PAYMENT_CURRENCY'])
        db.session.add(payment)

    intent = provider.create_payment(order)
    payment.provider = provider.name
    payment.intent_id = intent.intent_id
    payment.client_secret = intent.client_secret or None
    payment.status = 'created'
    payment.failure_reason = None
    db.session.flush()

    result = provider.confirm_payment(payment)
    _apply_payment_result(payment, result)
    return payment, result


def _apply_payment_result(payment, result):
    """Single place where a Payment row reacts to a gateway verdict."""
    order = payment.order
    if result.status == 'succeeded':
        payment.status = 'succeeded'
        payment.transaction_reference = result.reference or None
        payment.succeeded_at = datetime.utcnow()
        payment.failed_at = None
        payment.failure_reason = None
        order.payment_status = 'paid'
    elif result.status == 'processing':
        payment.status = 'processing'
        order.payment_status = 'pending'   # awaiting async webhook confirmation
    else:  # failed / canceled
        payment.status = 'failed'
        payment.failed_at = datetime.utcnow()
        payment.failure_reason = result.failure_reason or 'Payment declined'
        order.payment_status = 'pending'


def release_reservation(order):
    """Return reserved stock for an order that will never be fulfilled."""
    for line in order.items:
        item = CanteenItem.query.get(line.item_id)
        if item:
            item.stock_quantity += line.quantity


def finalize_confirmed_order(order):
    """
    Confirm a paid order: pickup token + QR + realistic estimate + one
    de-duplicated notification. Raises on failure so the caller can flag the
    payment/order mismatch - a success is never half-applied silently.
    """
    cfg = {
        'CANTEEN_TEACHER_PRIORITY_ENABLED': current_app.config['CANTEEN_TEACHER_PRIORITY_ENABLED'],
        'CANTEEN_TEACHER_RESERVE_RATIO': current_app.config['CANTEEN_TEACHER_RESERVE_RATIO'],
        'CANTEEN_AUTO_CONFIRM': current_app.config['CANTEEN_AUTO_CONFIRM'],
        'CANTEEN_MIN_LEAD_MINS': current_app.config['CANTEEN_MIN_LEAD_MINS'],
        'CANTEEN_PREP_MIN_PER_ORDER': current_app.config['CANTEEN_PREP_MIN_PER_ORDER'],
    }
    order.order_status = 'confirmed'
    order.confirmed_at = datetime.utcnow()
    if not order.pickup_token:
        order.pickup_token = secrets.token_urlsafe(24)
    db.session.flush()

    if order.slot_id:
        ahead, _total = booking.queue_position(order)
        order.estimated_ready_at = booking.estimate_ready_at(
            order.slot, booking.max_prep_minutes(order), ahead, cfg)

    qr_path = generate_order_qr(order, save_to_disk=True)
    if qr_path:
        order.qr_code_path = qr_path

    Notification.notify(
        order.user_id, "Canteen order confirmed",
        f"Order {order.order_code} is PAID and confirmed for pickup at "
        f"{order.estimated_ready_at.strftime('%H:%M') if order.estimated_ready_at else order.pickup_time.strftime('%H:%M')}. "
        "Show your QR code at the counter.",
        category='canteen',
        link_url=url_for('canteen.order_detail', order_code=order.order_code),
        dedup_key=f"canteen:{order.id}:confirmed",
    )
    db.session.commit()


def flag_confirm_mismatch(payment, error):
    """Payment captured but order confirmation failed - record, alert, keep money."""
    payment.confirm_mismatch = True
    db.session.add(AuditLog(
        action='PAYMENT_CONFIRM_MISMATCH', module='CANTEEN', user_id=payment.order.user_id,
        details=f"Payment {payment.intent_id} captured for order {payment.order.order_code} "
                f"but confirmation failed: {error}",
    ))
    db.session.commit()


def resolve_confirm_mismatch(order, admin_user):
    """Admin retry: re-run confirmation for a captured-but-unconfirmed order."""
    finalize_confirmed_order(order)
    order.payment.confirm_mismatch = False
    AuditLog.log(action='PAYMENT_MISMATCH_RESOLVED', module='CANTEEN', user_id=admin_user.id,
                 details=f"Order {order.order_code} confirmed after payment mismatch retry")


# ------------------------------------------------------------------- refunds

def record_complaint(order, user, note):
    """Step 1: record a refund complaint as a Refund row awaiting authorization."""
    refund = Refund.query.filter_by(order_id=order.id, status='requested').first()
    if not refund:
        refund = Refund(
            refund_reference=f"REF-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}",
            payment_id=order.payment.id if order.payment else None,
            order_id=order.id,
            amount=order.total_amount,
            currency=current_app.config['PAYMENT_CURRENCY'],
            status='requested',
            complaint_note=(note or 'Refund requested by customer')[:1000],
            requested_by=user.id if user else None,
        )
        refund.order = order
        if order.payment:
            refund.payment = order.payment
        db.session.add(refund)
    else:
        refund.complaint_note = (note or refund.complaint_note or '')[:1000]
    return refund


def initiate_refund(order, amount, reason, authorized_by, existing_refund=None):
    """
    Steps 2-8: verify order + payment, determine the applicable refund,
    require authorization, initiate through the gateway, track its reference,
    and update status only on reliable confirmation. Returns (refund, result).
    """
    provider = get_provider()
    payment = order.payment

    # 2. verification ------------------------------------------------------
    if not payment or payment.status != 'succeeded':
        return None, 'NO_PAYMENT'
    refundable = payment.refundable_amount
    amount = round(float(amount if amount and amount > 0 else refundable), 2)
    if amount <= 0 or amount > refundable:
        return None, 'AMOUNT_INVALID'

    # 1 + 4. complaint record + explicit authorization --------------------
    refund = existing_refund or Refund.query.filter_by(order_id=order.id, status='requested').first()
    if refund is None:
        refund = Refund(
            refund_reference=f"REF-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}",
            payment_id=payment.id, order_id=order.id,
            currency=payment.currency,
            complaint_note=(reason or 'Refund authorized by canteen staff')[:1000],
            requested_by=authorized_by.id if authorized_by else None,
        )
        db.session.add(refund)
        # Assign the relationships too (not just the FKs) so refund.payment /
        # refund.order are usable immediately on the pending row pre-flush.
        refund.payment = payment
        refund.order = order
    refund.payment_id = payment.id
    refund.amount = amount
    refund.is_partial = amount < float(payment.amount)
    refund.authorized_by = authorized_by.id if authorized_by else None
    refund.authorized_at = datetime.utcnow()

    # 5 + 6. initiate through the gateway and track its reference ----------
    result = provider.refund(payment, amount, reason or '')
    refund.attempts = (refund.attempts or 0) + 1
    refund.provider_refund_id = result.provider_refund_id or None
    refund.gateway_message = (result.message or '')[:255]
    refund.initiated_at = datetime.utcnow()

    if result.status == 'succeeded':
        refund.status = 'succeeded'
        _apply_refund_confirmation(refund)                 # 7. reliable confirmation
    elif result.status == 'processing':
        refund.status = 'processing'                       # delayed: webhook/re-sync later
        order.order_status = 'refund_processing' if order.order_status in booking.REFUND else order.order_status
    else:
        refund.status = 'failed'                           # visible failure, retry allowed

    db.session.flush()

    # 8. notify ------------------------------------------------------------
    if result.status == 'succeeded':
        _notify_refund(refund,
                       "Refund completed",
                       f"Refund of INR {amount:.2f} for order {order.order_code} "
                       f"({refund.refund_reference}) has been returned to your payment method.")
    elif result.status == 'processing':
        _notify_refund(refund,
                       "Refund processing",
                       f"Refund of INR {amount:.2f} for order {order.order_code} was initiated "
                       f"({refund.refund_reference}); your bank may take a few business days. "
                       f"Gateway reference: {refund.provider_refund_id}.")
    else:
        _notify_refund(refund,
                       "Refund attempt failed",
                       f"The refund for order {order.order_code} could not be completed "
                       f"({result.message}). The canteen team has been notified and will retry - "
                       "your money has NOT been lost.")

    AuditLog.log(
        action='CANTEEN_REFUND_INITIATED', module='CANTEEN',
        user_id=authorized_by.id if authorized_by else None,
        details=f"Order {order.order_code}: refund {refund.refund_reference} of "
                f"{amount:.2f} -> {result.status} (gateway {refund.provider_refund_id})",
    )
    db.session.commit()
    return refund, result


def retry_refund(refund, authorized_by):
    """Re-initiate a failed refund (e.g. after a gateway outage)."""
    order = refund.order
    payment = refund.payment
    if not order or not payment or refund.status not in ('failed', 'processing'):
        return refund, 'NOT_RETRYABLE'
    provider = get_provider()
    if refund.status == 'processing':
        # Re-sync a delayed refund with the gateway instead of double-refunding.
        result = provider.verify_refund(refund)
        if result.status == 'succeeded':
            refund.status = 'succeeded'
            refund.confirmed_at = datetime.utcnow()
            _apply_refund_confirmation(refund)
            _notify_refund(refund, "Refund completed",
                           f"Refund {refund.refund_reference} for order {order.order_code} "
                           "has now settled with your bank.")
            db.session.commit()
        elif result.status == 'failed':
            refund.status = 'failed'
            refund.gateway_message = (result.message or 'Gateway reported failure')[:255]
            db.session.commit()
        return refund, result
    refund.authorized_by = authorized_by.id if authorized_by else refund.authorized_by
    refund.authorized_at = datetime.utcnow()
    result = provider.refund(payment, float(refund.amount), refund.complaint_note or 'retry')
    refund.attempts += 1
    refund.provider_refund_id = result.provider_refund_id or refund.provider_refund_id
    refund.gateway_message = (result.message or '')[:255]
    refund.initiated_at = datetime.utcnow()
    if result.status == 'succeeded':
        refund.status = 'succeeded'
        _apply_refund_confirmation(refund)
        _notify_refund(refund, "Refund completed",
                       f"Retry succeeded: INR {float(refund.amount):.2f} for order "
                       f"{order.order_code} has been returned.")
    elif result.status == 'processing':
        refund.status = 'processing'
    else:
        refund.status = 'failed'
    db.session.commit()
    return refund, result


def _apply_refund_confirmation(refund):
    """Step 7: move payment/order state ONLY on reliable gateway confirmation."""
    payment = refund.payment
    order = refund.order
    refund.confirmed_at = refund.confirmed_at or datetime.utcnow()
    payment.refunded_amount = float(payment.refunded_amount or 0) + float(refund.amount)
    fully = payment.refunded_amount >= float(payment.amount) - 0.005
    payment.status = 'refunded' if fully else 'partially_refunded'
    order.payment_status = 'refunded' if fully else 'partially_refunded'
    if fully and order.order_status in booking.REFUND + ('pending', 'confirmed', 'preparing', 'ready'):
        order.order_status = 'refunded'


def _notify_refund(refund, title, message):
    order = refund.order
    Notification.notify(
        order.user_id, title, message, category='canteen',
        link_url=url_for('canteen.order_detail', order_code=order.order_code),
        dedup_key=f"canteen:{order.id}:refund:{refund.refund_reference}:{refund.status}",
    )


# ------------------------------------------------------------------ webhooks

_SUCCESS_TYPES = {'payment_intent.succeeded', 'payment.succeeded'}
_FAIL_TYPES = {'payment_intent.payment_failed', 'payment.failed'}
_REFUND_TYPES = {'charge.refund.updated', 'refund.updated'}


def process_webhook_event(provider_name, event: dict) -> str:
    """
    Handle one signature-verified gateway event exactly once.
    Returns 'processed', 'duplicate', 'ignored' or 'failed'.
    """
    event_id = (event.get('id') or '').strip()
    event_type = event.get('type') or ''
    if not event_id or not event_type:
        return 'ignored'

    record = WebhookEvent(provider=provider_name, event_id=event_id, event_type=event_type,
                          payload=json.dumps(event)[:4000])
    db.session.add(record)
    try:
        db.session.flush()           # unique event_id -> duplicate delivered here
    except IntegrityError:
        db.session.rollback()
        return 'duplicate'

    data = event.get('data') or {}
    try:
        if event_type in _SUCCESS_TYPES:
            _on_payment_success(data)
        elif event_type in _FAIL_TYPES:
            _on_payment_failure(data)
        elif event_type in _REFUND_TYPES:
            _on_refund_update(data)
        else:
            record.status = 'ignored'
            db.session.commit()
            return 'ignored'
        record.status = 'processed'
        record.processed_at = datetime.utcnow()
        db.session.commit()
        return 'processed'
    except Exception as exc:                       # noqa: BLE001 - record & surface
        db.session.rollback()
        fresh = WebhookEvent.query.filter_by(event_id=event_id).first()
        if fresh:
            fresh.status, fresh.error = 'failed', str(exc)[:250]
            db.session.commit()
        current_app.logger.error(f"Webhook {event_id} ({event_type}) failed: {exc}")
        return 'failed'


def _on_payment_success(data):
    intent_id = data.get('intent_id') or data.get('id') or ''
    payment = Payment.query.filter_by(intent_id=intent_id).first()
    if not payment or payment.status == 'succeeded':
        return                                    # idempotent replay guard
    # The signature-verified webhook IS the backend confirmation for async
    # payments; the transaction reference is recorded from the event payload.
    payment.status = 'succeeded'
    payment.succeeded_at = datetime.utcnow()
    payment.transaction_reference = data.get('reference') or payment.intent_id
    payment.order.payment_status = 'paid'
    db.session.commit()
    order = payment.order
    if order.order_status in booking.PENDING:
        try:
            finalize_confirmed_order(order)
        except Exception as exc:                   # money captured, order not confirmable
            payment.confirm_mismatch = True
            flag_confirm_mismatch(payment, exc)
    elif order.order_status in ('cancelled', 'refunded'):
        # Money arrived for an order that no longer exists in the pipeline -
        # never keep it silently; an admin refunds or restores via the console.
        payment.confirm_mismatch = True
        flag_confirm_mismatch(payment, f"payment captured after order was {order.order_status}")


def _on_payment_failure(data):
    intent_id = data.get('intent_id') or data.get('id') or ''
    payment = Payment.query.filter_by(intent_id=intent_id).first()
    if not payment or payment.status in ('failed', 'refunded', 'partially_refunded'):
        return
    payment.status = 'failed'
    payment.failed_at = datetime.utcnow()
    payment.failure_reason = (data.get('failure_reason') or 'Payment failed at the gateway')[:500]
    order = payment.order
    order.payment_status = 'pending'
    if order.order_status in booking.PENDING + ('confirmed',):
        release_reservation(order)                # reservation released, never silently
        order.order_status = 'cancelled'
        order.refund_reason = 'Payment failed - order not charged'
        Notification.notify(
            order.user_id, "Payment failed",
            f"Payment for order {order.order_code} failed: {payment.failure_reason}. "
            "Nothing was charged and your order was not placed.",
            category='canteen',
            link_url=url_for('canteen.my_orders'),
            dedup_key=f"canteen:{order.id}:payment_failed",
        )
    db.session.commit()


def _on_refund_update(data):
    refund_id = data.get('provider_refund_id') or data.get('refund_id') or ''
    status = data.get('status') or ''
    refund = Refund.query.filter_by(provider_refund_id=refund_id).first()
    if not refund:
        return
    if status in ('succeeded', 'success') and refund.status != 'succeeded':
        refund.status = 'succeeded'
        _apply_refund_confirmation(refund)
        _notify_refund(refund, "Refund completed",
                       f"Refund {refund.refund_reference} for order {refund.order.order_code} "
                       "has been confirmed by the payment gateway.")
    elif status in ('failed', 'cancelled') and refund.status != 'failed':
        refund.status = 'failed'
        refund.gateway_message = 'Gateway webhook reported refund failure'
        _notify_refund(refund, "Refund attempt failed",
                       f"The gateway could not settle refund {refund.refund_reference} for "
                       f"order {refund.order.order_code}. The canteen team will retry - your "
                       "money has not been lost.")
    db.session.commit()
