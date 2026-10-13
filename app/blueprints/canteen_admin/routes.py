from datetime import datetime, date, timedelta
from pathlib import Path
import secrets
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from app.blueprints.canteen_admin import canteen_admin_bp
from app.models import (
    CanteenOrder, CanteenOrderItem, CanteenItem, CanteenCategory,
    CanteenPickupSlot, Notification, AuditLog, Payment, Refund, WebhookEvent,
)
from app.database import db
from app.utils.auth_helpers import role_required, get_current_user
from app.utils.qr_generator import generate_order_qr, parse_pickup_payload
from app.utils.image_matcher import validate_image_bytes
from app.utils import canteen_booking as booking
from app.utils import payment_service

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_PHOTO_BYTES = 8 * 1024 * 1024

def _booking_config():
    cfg = current_app.config
    return {
        'CANTEEN_TEACHER_PRIORITY_ENABLED': cfg['CANTEEN_TEACHER_PRIORITY_ENABLED'],
        'CANTEEN_TEACHER_RESERVE_RATIO': cfg['CANTEEN_TEACHER_RESERVE_RATIO'],
        'CANTEEN_AUTO_CONFIRM': cfg['CANTEEN_AUTO_CONFIRM'],
        'CANTEEN_MIN_LEAD_MINS': cfg['CANTEEN_MIN_LEAD_MINS'],
        'CANTEEN_PREP_MIN_PER_ORDER': cfg['CANTEEN_PREP_MIN_PER_ORDER'],
    }

def _notify_order(order, title, message):
    """One notification per (order, status) - replays can never duplicate it."""
    Notification.notify(
        order.user_id, title, message,
        category='canteen',
        link_url=url_for('canteen.order_detail', order_code=order.order_code),
        dedup_key=f"canteen:{order.id}:{order.order_status}",
    )

def _save_food_photo(file, item) -> str | None:
    """Validate + persist an uploaded dish photo; returns the /static URL."""
    filename = file.filename or ''
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Photo rejected: only PNG, JPG, JPEG or WEBP images are allowed.")
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise ValueError("Photo rejected: file exceeds the 8 MB limit.")
    if not validate_image_bytes(file):
        raise ValueError("Photo rejected: file content is not a valid image.")
    safe = secure_filename(f"canteen_{item.id or 'new'}_{int(datetime.utcnow().timestamp())}_{filename}")
    upload_dir = Path(current_app.root_path) / "static" / "uploads" / "canteen"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file.save(upload_dir / safe)
    return f"/static/uploads/canteen/{safe}"

# ---------------------------------------------------------------- dashboard

@canteen_admin_bp.route('/dashboard')
@role_required(['canteen_admin', 'main_admin'])
def dashboard():
    """
    Canteen Operator Command Center:
    Orders queue with strict Teacher-First Priority sorting,
    preparation controls, refund queue, and inventory overview.
    """
    user = get_current_user()

    # Priority sorting: Teachers (is_priority=True) first, then by earliest pickup time
    active_orders = (
        CanteenOrder.query
        .filter(CanteenOrder.order_status.in_(booking.ACTIVE + booking.REFUND))
        .order_by(CanteenOrder.is_priority.desc(), CanteenOrder.pickup_time.asc())
        .all()
    )

    recent_completed = (
        CanteenOrder.query
        .filter(CanteenOrder.order_status.in_(('collected', 'cancelled', 'refunded')))
        .order_by(CanteenOrder.updated_at.desc())
        .limit(10)
        .all()
    )

    total_items = CanteenItem.query.count()
    low_stock_items = CanteenItem.query.filter(CanteenItem.stock_quantity < 10).all()

    # Financial aggregate
    total_sales = db.session.query(db.func.sum(CanteenOrder.total_amount)).filter_by(payment_status='paid').scalar() or 0.0

    # Phase 6 live stats
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    orders_today = CanteenOrder.query.filter(CanteenOrder.created_at >= today_start).count()
    pending_count = CanteenOrder.query.filter(CanteenOrder.order_status.in_(booking.PENDING)).count()
    refund_count = CanteenOrder.query.filter(CanteenOrder.order_status.in_(booking.REFUND)).count()
    open_slots = [
        booking.slot_availability(s, _booking_config(), True)
        for s in booking.upcoming_slots(days=3)
    ]

    # ---- Phase 7 payment/refund console ----------------------------------
    refund_cases = (
        Refund.query
        .filter(Refund.status.in_(('requested', 'processing', 'failed')))
        .order_by(Refund.created_at.desc())
        .limit(25).all()
    )
    mismatch_orders = (
        CanteenOrder.query.join(Payment, Payment.order_id == CanteenOrder.id)
        .filter(Payment.confirm_mismatch.is_(True))
        .order_by(CanteenOrder.created_at.desc()).limit(10).all()
    )
    captured_total = float(
        db.session.query(db.func.sum(Payment.amount))
        .filter(Payment.status.in_(('succeeded', 'partially_refunded', 'refunded'))).scalar() or 0.0)
    refunded_total = float(
        db.session.query(db.func.sum(Refund.amount))
        .filter(Refund.status == 'succeeded').scalar() or 0.0)

    return render_template(
        'canteen_admin/dashboard.html',
        user=user,
        active_orders=active_orders,
        recent_completed=recent_completed,
        total_items=total_items,
        low_stock_items=low_stock_items,
        total_sales=float(total_sales),
        orders_today=orders_today,
        pending_count=pending_count,
        refund_count=refund_count,
        open_slots=open_slots,
        booking=booking,
        refund_cases=refund_cases,
        mismatch_orders=mismatch_orders,
        captured_total=captured_total,
        refunded_total=refunded_total,
    )

# ---------------------------------------------------------------- lifecycle

@canteen_admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def update_order_status(order_id):
    """Phase 6: guarded order lifecycle transitions with customer notifications."""
    order = CanteenOrder.query.get_or_404(order_id)
    new_status = request.form.get('new_status')
    previous_status = order.order_status

    valid_statuses = set(booking.PENDING + booking.ACTIVE + booking.TERMINAL + booking.REFUND) | {'placed'}
    if new_status not in valid_statuses or not booking.can_transition(previous_status, new_status):
        flash(f"Illegal transition {previous_status.upper()} → {(new_status or '?').upper()} for order #{order.order_code}.", "danger")
        return redirect(url_for('canteen_admin.dashboard'))

    if new_status == 'confirmed':
        order.confirmed_at = datetime.utcnow()
        if not order.pickup_token:
            order.pickup_token = secrets.token_urlsafe(24)
    elif new_status == 'collected':
        order.collected_at = datetime.utcnow()
    elif new_status in ('cancelled', 'refunded'):
        # Uncooked food goes back into stock; cooked food does not.
        if previous_status in booking.PENDING + ('confirmed',):
            for line in order.items:
                item = CanteenItem.query.get(line.item_id)
                if item:
                    item.stock_quantity += line.quantity
        order.refund_reason = request.form.get('refund_reason') or order.refund_reason or \
            ('Cancelled by canteen staff' if new_status == 'cancelled' else 'Refund processed by canteen staff')
        # ---- Phase 7: a captured online payment must be refunded THROUGH the
        # gateway. The status column is never flipped to fake a refund, so a
        # paid student order can never be silently cancelled.
        if order.payment and order.payment.status in ('succeeded', 'partially_refunded'):
            order.order_status = 'refund_processing'
            db.session.flush()
            admin = get_current_user()
            refund, result = payment_service.initiate_refund(
                order, None, order.refund_reason, admin)
            if new_status == 'cancelled':
                order.order_status = 'cancelled'
                _notify_order(order, "Order cancelled",
                              f"Order {order.order_code} was cancelled by the canteen. "
                              "Your payment is being returned via the original method.")
            db.session.commit()
            AuditLog.log(
                action='CANTEEN_ORDER_STATUS', module='CANTEEN', user_id=admin.id,
                details=f"Order {order.order_code}: {previous_status} → {new_status} via "
                        f"gateway refund {getattr(refund, 'refund_reference', '-')} "
                        f"({getattr(result, 'status', result)})",
                ip_address=request.remote_addr,
            )
            if refund is None:
                flash(f"Order #{order.order_code}: gateway refund could not start ({result}).", "danger")
            elif refund.status == 'succeeded':
                flash(f"Gateway refund {refund.refund_reference} CONFIRMED settled (sandbox/test mode).", "success")
            elif refund.status == 'processing':
                flash(f"Gateway refund {refund.refund_reference} accepted but not yet settled - "
                      "it stays visible in the refund queue for re-sync.", "info")
            else:
                flash(f"Gateway refund FAILED at the provider. The order stays visible for retry; "
                      "no money has been returned yet.", "warning")
            return redirect(url_for('canteen_admin.dashboard'))
        order.payment_status = 'refunded'  # legacy/cash record with no gateway capture

    order.order_status = new_status

    # Manual confirmation still needs the QR image written for the customer
    if new_status == 'confirmed':
        db.session.commit()
        qr_path = generate_order_qr(order, save_to_disk=True)
        if qr_path:
            order.qr_code_path = qr_path

    messages = {
        'confirmed': ("Order confirmed", "Your order {code} is confirmed. Show your QR code at pickup."),
        'preparing': ("Order in the kitchen", "Your order {code} is now being prepared."),
        'ready': ("Order ready for pickup", "Your order {code} is READY. Please collect it at the canteen counter."),
        'collected': ("Order collected", "Order {code} was collected. Enjoy your meal!"),
        'cancelled': ("Order cancelled", "Order {code} was cancelled by the canteen. Payment will be returned."),
        'refund_requested': ("Refund requested", "Your refund request for {code} was recorded."),
        'refund_processing': ("Refund processing", "The refund for order {code} is now being processed."),
        'refunded': ("Refund completed", "The refund for order {code} has been returned to your payment method."),
    }
    if new_status in messages:
        title, body = messages[new_status]
        _notify_order(order, title, body.format(code=order.order_code))

    db.session.commit()

    AuditLog.log(
        action='CANTEEN_ORDER_STATUS',
        module='CANTEEN',
        user_id=get_current_user().id,
        details=f"Order {order.order_code}: {previous_status} → {new_status}",
        ip_address=request.remote_addr,
    )
    flash(f"Order #{order.order_code} status updated to {order.status_label.upper()}.", "success")
    return redirect(url_for('canteen_admin.dashboard'))

# ---------------------------------------------------------------- refunds (Phase 7)

@canteen_admin_bp.route('/orders/<int:order_id>/refund', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def process_refund(order_id):
    """
    Phase 7 refund console: verify the payment, authorise a FULL or PARTIAL
    amount and initiate it through the gateway. Customer complaints recorded
    via 'Request Refund' are picked up automatically from the queue.
    """
    order = CanteenOrder.query.get_or_404(order_id)
    admin = get_current_user()
    raw_amount = request.form.get('amount', '').strip()
    reason = (request.form.get('refund_reason') or order.refund_reason or
              'Refund authorised by canteen staff').strip()[:500]

    amount = None
    if raw_amount:
        try:
            amount = round(float(raw_amount), 2)
        except ValueError:
            flash("Invalid refund amount - enter a number like 45.50 (leave blank for the full amount).", "danger")
            return redirect(url_for('canteen_admin.dashboard'))

    # No captured gateway payment: cash/legacy path. Mark it locally and say
    # plainly that no gateway transfer happened - never fake a money movement.
    if not order.payment or order.payment.status not in ('succeeded', 'partially_refunded'):
        order.order_status = 'refunded'
        order.payment_status = 'refunded'
        order.refund_reason = reason
        db.session.commit()
        _notify_order(order, "Refund completed",
                      f"Order {order.order_code} was marked refunded by the canteen "
                      "(cash/legacy settlement - no gateway capture on record).")
        AuditLog.log(action='CANTEEN_REFUND_AUTHORIZED', module='CANTEEN', user_id=admin.id,
                     details=f"Order {order.order_code}: cash/legacy refund marked (no gateway payment)",
                     ip_address=request.remote_addr)
        flash(f"Order #{order.order_code} marked REFUNDED (cash/legacy - no gateway payment on record).", "info")
        return redirect(url_for('canteen_admin.dashboard'))

    refund, result = payment_service.initiate_refund(order, amount, reason, admin)
    if refund is None:
        msg = ("Refund refused: the amount exceeds the still-refundable balance."
               if result == 'AMOUNT_INVALID' else f"Refund could not be initiated ({result}).")
        flash(msg, "danger")
        return redirect(url_for('canteen_admin.dashboard'))

    order.refund_reason = reason
    if refund.status != 'succeeded' and order.order_status in booking.REFUND + ('pending', 'confirmed', 'preparing', 'ready'):
        order.order_status = 'refund_processing'
    db.session.commit()
    AuditLog.log(
        action='CANTEEN_REFUND_AUTHORIZED', module='CANTEEN', user_id=admin.id,
        details=f"Order {order.order_code}: authorised {refund.refund_reference} "
                f"₹{float(refund.amount):.2f} ({'partial' if refund.is_partial else 'full'}) -> {refund.status}",
        ip_address=request.remote_addr,
    )
    if refund.status == 'succeeded':
        flash(f"Gateway refund {refund.refund_reference} CONFIRMED settled (sandbox/test mode).", "success")
    elif refund.status == 'processing':
        flash(f"Gateway refund {refund.refund_reference} accepted; settlement pending with the bank - "
              "re-sync it from the refund queue.", "info")
    else:
        flash(f"Gateway refund attempt FAILED ({refund.gateway_message}). It stays visible in the queue "
              "for retry - the customer's money has not been lost.", "warning")
    return redirect(url_for('canteen_admin.dashboard'))

@canteen_admin_bp.route('/refunds/<int:refund_id>/retry', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def retry_refund(refund_id):
    """Re-sync a delayed ('processing') refund or re-initiate a failed one."""
    refund = Refund.query.get_or_404(refund_id)
    admin = get_current_user()
    refund, result = payment_service.retry_refund(refund, admin)
    db.session.commit()
    AuditLog.log(action='CANTEEN_REFUND_RETRY', module='CANTEEN', user_id=admin.id,
                 details=f"Refund {refund.refund_reference}: {result if isinstance(result, str) else result.status} "
                         f"(attempt {refund.attempts})", ip_address=request.remote_addr)
    if refund.status == 'succeeded':
        flash(f"Refund {refund.refund_reference} is now CONFIRMED settled.", "success")
    elif refund.status == 'processing':
        flash(f"Refund {refund.refund_reference} is still settling with the bank "
              "(the gateway has not confirmed it yet).", "info")
    elif result == 'NOT_RETRYABLE':
        flash("This refund record is not in a retryable state.", "warning")
    else:
        flash(f"Retry failed again at the gateway ({refund.gateway_message}). It remains visible for another attempt.", "warning")
    return redirect(url_for('canteen_admin.dashboard'))

@canteen_admin_bp.route('/orders/<int:order_id>/resolve-mismatch', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def resolve_payment_mismatch(order_id):
    """
    Phase 7: 'payment captured but order confirmation failed' - admin retry.
    Either the order gets confirmed properly (QR + notification) or the admin
    sends it to the refund console; the money is never left unaccounted.
    """
    order = CanteenOrder.query.get_or_404(order_id)
    admin = get_current_user()
    if not (order.payment and order.payment.confirm_mismatch):
        flash("No open payment/order mismatch on this order.", "info")
        return redirect(url_for('canteen_admin.dashboard'))
    try:
        payment_service.resolve_confirm_mismatch(order, admin)
        db.session.commit()
        flash(f"Order #{order.order_code} confirmed and QR issued - payment mismatch resolved.", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Could not confirm the order ({exc}). Use the refund console to return the payment instead.", "danger")
    return redirect(url_for('canteen_admin.dashboard'))

# ---------------------------------------------------------------- QR pickup

@canteen_admin_bp.route('/verify-pickup', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def verify_pickup():
    """
    Phase 6: verify pickup from a scanned QR payload (or manually entered code).
    - The opaque per-order token inside the QR is checked server-side.
    - Each code can be redeemed exactly once (double pickup is refused).
    - Cancelled / refunded orders can never be redeemed.
    """
    raw = request.form.get('order_code', '').strip()
    order_code, token = parse_pickup_payload(raw)

    if not order_code:
        flash("Unrecognized QR payload. Ask the customer to reopen their pickup QR.", "danger")
        return redirect(url_for('canteen_admin.dashboard'))

    order = CanteenOrder.query.filter_by(order_code=order_code.upper()).first()

    if not order:
        flash(f"No order found with code '{order_code}'.", "danger")
        AuditLog.log(action='CANTEEN_PICKUP_REJECTED', module='CANTEEN',
                     user_id=get_current_user().id,
                     details=f"Unknown code scanned: {raw[:80]}",
                     ip_address=request.remote_addr)
        return redirect(url_for('canteen_admin.dashboard'))

    # Token check: Phase 6 orders MUST present the secret inside their QR.
    if order.pickup_token:
        if not token or not secrets.compare_digest(str(order.pickup_token), str(token)):
            flash(f"QR token mismatch for #{order.order_code} - handover refused. "
                  "Ask the customer to reopen the original QR from their order page.", "danger")
            AuditLog.log(action='CANTEEN_PICKUP_REJECTED', module='CANTEEN',
                         user_id=get_current_user().id,
                         details=f"Bad token for order {order.order_code}",
                         ip_address=request.remote_addr)
            return redirect(url_for('canteen_admin.dashboard'))

    # Single redemption
    if order.order_status == 'collected':
        flash(f"Order #{order.order_code} was ALREADY COLLECTED at {order.collected_at}. Duplicate redemption refused.", "warning")
        return redirect(url_for('canteen_admin.dashboard'))

    if order.order_status in ('cancelled', 'refunded') or order.order_status in booking.REFUND:
        flash(f"Order #{order.order_code} is {order.status_label} and can no longer be picked up.", "danger")
        return redirect(url_for('canteen_admin.dashboard'))

    if order.order_status in booking.PENDING:
        flash(f"Order #{order.order_code} is not confirmed yet - confirm it in the queue first.", "warning")
        return redirect(url_for('canteen_admin.dashboard'))

    order.order_status = 'collected'
    order.collected_at = datetime.utcnow()
    if order.payment_status == 'pending':
        order.payment_status = 'paid'  # cash collected at the counter

    _notify_order(order, "Order collected",
                  f"Order {order.order_code} was marked COLLECTED at the canteen counter.")
    db.session.commit()

    AuditLog.log(action='CANTEEN_PICKUP_VERIFIED', module='CANTEEN',
                 user_id=get_current_user().id,
                 details=f"Order {order.order_code} pickup verified",
                 ip_address=request.remote_addr)

    flash(f"Success! Order #{order.order_code} verified and marked COLLECTED for {order.customer.full_name} ({order.user_role_at_order.title()}).", "success")
    return redirect(url_for('canteen_admin.dashboard'))

# ---------------------------------------------------------------- menu mgmt

@canteen_admin_bp.route('/menu', methods=['GET', 'POST'])
@role_required(['canteen_admin', 'main_admin'])
def menu_manage():
    """Manage canteen menu items: add with photo, stock, prep time."""
    user = get_current_user()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_item':
            name = request.form.get('name', '').strip()
            category_id = int(request.form.get('category_id') or 0)
            price = float(request.form.get('price', 0.0))
            stock = int(request.form.get('stock_quantity', 50))
            prep = int(request.form.get('preparation_time_mins', 10))
            description = request.form.get('description', '')

            item = CanteenItem(
                name=name,
                category_id=category_id,
                price=price,
                stock_quantity=stock,
                preparation_time_mins=max(1, prep),
                description=description,
                is_available=True
            )
            db.session.add(item)
            db.session.flush()

            file = request.files.get('photo')
            if file and file.filename:
                try:
                    item.photo_url = _save_food_photo(file, item)
                except ValueError as exc:
                    db.session.rollback()
                    flash(str(exc), "danger")
                    return redirect(url_for('canteen_admin.menu_manage'))

            db.session.commit()
            AuditLog.log(action='CANTEEN_ITEM_ADDED', module='CANTEEN', user_id=user.id,
                         details=f"Menu item '{name}' added (₹{price}, stock {stock}).",
                         ip_address=request.remote_addr)
            flash(f"Item '{name}' added to menu.", "success")
            return redirect(url_for('canteen_admin.menu_manage'))

    items = CanteenItem.query.order_by(CanteenItem.category_id.asc(), CanteenItem.name.asc()).all()
    categories = CanteenCategory.query.order_by(CanteenCategory.display_order.asc()).all()

    return render_template('canteen_admin/menu_manage.html', user=user, items=items, categories=categories)

@canteen_admin_bp.route('/menu/edit/<int:item_id>', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def item_edit(item_id):
    """Phase 6: edit dish details - name, category, price, stock, prep time, photo."""
    item = CanteenItem.query.get_or_404(item_id)

    name = request.form.get('name', '').strip()
    if name:
        item.name = name
    category_id = request.form.get('category_id', type=int)
    if category_id and CanteenCategory.query.get(category_id):
        item.category_id = category_id
    price = request.form.get('price')
    if price not in (None, '') and float(price) >= 0:
        item.price = float(price)
    stock = request.form.get('stock_quantity')
    if stock not in (None, ''):
        item.stock_quantity = max(0, int(stock))
    prep = request.form.get('preparation_time_mins')
    if prep not in (None, ''):
        item.preparation_time_mins = max(1, int(prep))
    description = request.form.get('description')
    if description is not None:
        item.description = description
    if request.form.get('is_available') in ('1', 'true', 'on'):
        item.is_available = True

    file = request.files.get('photo')
    if file and file.filename:
        try:
            item.photo_url = _save_food_photo(file, item)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for('canteen_admin.menu_manage'))

    db.session.commit()
    AuditLog.log(action='CANTEEN_ITEM_UPDATED', module='CANTEEN', user_id=get_current_user().id,
                 details=f"Menu item '{item.name}' updated (₹{item.price}, stock {item.stock_quantity}).",
                 ip_address=request.remote_addr)
    flash(f"Item '{item.name}' updated.", "success")
    return redirect(url_for('canteen_admin.menu_manage'))

@canteen_admin_bp.route('/menu/toggle/<int:item_id>', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def toggle_item(item_id):
    """Toggle item availability."""
    item = CanteenItem.query.get_or_404(item_id)
    item.is_available = not item.is_available
    db.session.commit()
    status_str = "Available" if item.is_available else "Sold Out / Disabled"
    flash(f"Item '{item.name}' marked as {status_str}.", "info")
    return redirect(url_for('canteen_admin.menu_manage'))

# ---------------------------------------------------------------- slots

@canteen_admin_bp.route('/slots', methods=['GET', 'POST'])
@role_required(['canteen_admin', 'main_admin'])
def manage_slots():
    """Phase 6: configure pickup slots (date, window, order capacity)."""
    user = get_current_user()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slot_date_str = request.form.get('slot_date', '')
        start_time = request.form.get('start_time', '')
        end_time = request.form.get('end_time', '')
        capacity = request.form.get('order_capacity', type=int)

        errors = []
        if not name:
            errors.append("Slot name is required.")
        try:
            slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
        except ValueError:
            slot_date = None
            errors.append("Valid slot date required (YYYY-MM-DD).")
        try:
            datetime.strptime(start_time, '%H:%M')
            datetime.strptime(end_time, '%H:%M')
        except ValueError:
            errors.append("Start and end times must be HH:MM.")
            start_time = end_time = '00:00'
        if start_time >= end_time:
            errors.append("Slot end time must be after its start time.")
        if not capacity or capacity < 1:
            errors.append("Order capacity must be at least 1.")
        if slot_date and slot_date < date.today():
            errors.append("Slot date cannot be in the past.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(url_for('canteen_admin.manage_slots'))

        slot = CanteenPickupSlot(
            name=name, slot_date=slot_date, start_time=start_time,
            end_time=end_time, order_capacity=capacity,
        )
        db.session.add(slot)
        db.session.commit()
        AuditLog.log(action='CANTEEN_SLOT_CREATED', module='CANTEEN', user_id=user.id,
                     details=f"Pickup slot '{name}' {slot_date} {start_time}-{end_time} (cap {capacity}).",
                     ip_address=request.remote_addr)
        flash(f"Pickup slot '{name}' created.", "success")
        return redirect(url_for('canteen_admin.manage_slots'))

    cfg = _booking_config()
    slots = booking.upcoming_slots(days=14)
    slot_views = []
    for s in slots:
        info = booking.slot_availability(s, cfg, True)
        slot_views.append(info)

    return render_template('canteen_admin/slots.html', user=user, slots=slots, slot_views=slot_views)

@canteen_admin_bp.route('/slots/<int:slot_id>/toggle', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def toggle_slot(slot_id):
    """Open/close a pickup slot for new bookings."""
    slot = CanteenPickupSlot.query.get_or_404(slot_id)
    slot.is_active = not slot.is_active
    db.session.commit()
    state = "opened for bookings" if slot.is_active else "closed to new bookings"
    flash(f"Slot '{slot.name}' {state}.", "info")
    return redirect(url_for('canteen_admin.manage_slots'))

# ---------------------------------------------------------------- reports

@canteen_admin_bp.route('/reports')
@role_required(['canteen_admin', 'main_admin'])
def reports():
    """Phase 6: canteen operations report (sales, statuses, top items, slots)."""
    user = get_current_user()
    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    week_start = day_start - timedelta(days=6)

    def _sum(filter_query):
        return float(filter_query.scalar() or 0.0)

    revenue_today = _sum(db.session.query(db.func.sum(CanteenOrder.total_amount))
                         .filter(CanteenOrder.created_at >= day_start,
                                 CanteenOrder.order_status.notin_(('cancelled', 'refunded'))))
    revenue_week = _sum(db.session.query(db.func.sum(CanteenOrder.total_amount))
                        .filter(CanteenOrder.created_at >= week_start,
                                CanteenOrder.order_status.notin_(('cancelled', 'refunded'))))

    status_counts = {}
    for label in ('Pending', 'Confirmed', 'Preparing', 'Ready for Pickup', 'Collected',
                  'Cancelled', 'Refund Requested', 'Refund Processing', 'Refunded'):
        status_counts[label] = 0
    rows = db.session.query(CanteenOrder.order_status, db.func.count(CanteenOrder.id)) \
                     .filter(CanteenOrder.created_at >= week_start).group_by(CanteenOrder.order_status).all()
    for raw_status, count in rows:
        label = CanteenOrder.STATUS_LABELS.get(raw_status, raw_status.title())
        status_counts[label] = status_counts.get(label, 0) + count

    orders_week = db.session.query(db.func.count(CanteenOrder.id)) \
                            .filter(CanteenOrder.created_at >= week_start).scalar() or 0
    refunds_week = CanteenOrder.query.filter(
        CanteenOrder.created_at >= week_start,
        CanteenOrder.order_status.in_(booking.REFUND + ('refunded', 'cancelled'))).count()

    top_item_rows = (
        db.session.query(CanteenOrderItem.item_name, db.func.sum(CanteenOrderItem.quantity).label('qty'))
        .join(CanteenOrder, CanteenOrderItem.order_id == CanteenOrder.id)
        .filter(CanteenOrder.created_at >= week_start,
                CanteenOrder.order_status.notin_(('cancelled', 'refunded')))
        .group_by(CanteenOrderItem.item_name)
        .order_by(db.text('qty DESC'))
        .limit(5).all()
    )
    top_items = [{'name': n, 'qty': int(q or 0)} for n, q in top_item_rows]

    slot_utilization = []
    for slot in booking.upcoming_slots(days=7):
        booked, teacher_booked = booking.slot_booked_counts(slot.id)
        slot_utilization.append({
            'slot': slot,
            'booked': booked,
            'teacher_booked': teacher_booked,
            'capacity': slot.order_capacity,
            'pct': round(100.0 * booked / slot.order_capacity, 1) if slot.order_capacity else 0,
        })

    low_stock = CanteenItem.query.filter(CanteenItem.stock_quantity < 10).order_by(CanteenItem.stock_quantity.asc()).limit(10).all()

    return render_template(
        'canteen_admin/reports.html',
        user=user,
        revenue_today=revenue_today,
        revenue_week=revenue_week,
        orders_week=orders_week,
        refunds_week=refunds_week,
        status_counts=status_counts,
        top_items=top_items,
        slot_utilization=slot_utilization,
        low_stock=low_stock,
    )
