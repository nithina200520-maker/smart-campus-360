from datetime import datetime, timedelta
import random
import secrets
from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app
from app.blueprints.canteen import canteen_bp
from app.models import (
    CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem,
    CanteenPickupSlot, Notification, AuditLog,
)
from app.database import db
from app.utils.auth_helpers import login_required, get_current_user
from app.utils.qr_generator import generate_order_qr
from app.utils import canteen_booking as booking

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def _booking_config():
    cfg = current_app.config
    return {
        'CANTEEN_TEACHER_PRIORITY_ENABLED': cfg['CANTEEN_TEACHER_PRIORITY_ENABLED'],
        'CANTEEN_TEACHER_RESERVE_RATIO': cfg['CANTEEN_TEACHER_RESERVE_RATIO'],
        'CANTEEN_AUTO_CONFIRM': cfg['CANTEEN_AUTO_CONFIRM'],
        'CANTEEN_MIN_LEAD_MINS': cfg['CANTEEN_MIN_LEAD_MINS'],
        'CANTEEN_PREP_MIN_PER_ORDER': cfg['CANTEEN_PREP_MIN_PER_ORDER'],
    }

def _is_priority_user(user):
    """Teacher-first allocation applies to VERIFIED teachers only."""
    return bool(user and user.role == 'teacher' and user.is_verified)

@canteen_bp.route('/')
def index():
    """Module 3: Smart Canteen Menu with Phase 6 search and filtering."""
    user = get_current_user()
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort', 'default')

    categories = CanteenCategory.query.filter_by(is_active=True).order_by(CanteenCategory.display_order.asc()).all()

    menu_sections = []
    for cat in categories:
        if category_id and cat.id != category_id:
            continue
        items = [i for i in cat.items]
        if q:
            needle = q.lower()
            items = [i for i in items
                     if needle in i.name.lower() or needle in (i.description or '').lower()]
        if sort == 'price_asc':
            items.sort(key=lambda i: float(i.price))
        elif sort == 'price_desc':
            items.sort(key=lambda i: -float(i.price))
        elif sort == 'name':
            items.sort(key=lambda i: i.name.lower())
        if items:
            menu_sections.append({'category': cat, 'dishes': items})

    cart = session.get('canteen_cart', {})
    cart_total_count = sum(cart.values())

    return render_template(
        'canteen/index.html',
        user=user,
        menu_sections=menu_sections,
        categories=categories,
        cart=cart,
        cart_total_count=cart_total_count,
        q=q,
        selected_category=category_id,
        sort=sort,
        result_count=sum(len(s['dishes']) for s in menu_sections),
    )

@canteen_bp.route('/cart')
@login_required
def cart_view():
    """Shopping cart with Phase 6 pickup-slot selection."""
    user = get_current_user()
    cart = session.get('canteen_cart', {})

    cart_items = []
    subtotal = 0.0

    for item_id_str, qty in cart.items():
        item = CanteenItem.query.get(int(item_id_str))
        if item and item.is_available:
            item_total = float(item.price) * qty
            subtotal += item_total
            cart_items.append({
                "item": item,
                "quantity": qty,
                "total": item_total
            })

    cfg = _booking_config()
    priority = _is_priority_user(user)
    slot_options = booking.bookable_slots(cfg, priority)

    # Earliest pickup is 15 minutes from now
    min_pickup = (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M')
    max_pickup = (datetime.now() + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M')

    return render_template(
        'canteen/cart.html',
        user=user,
        cart_items=cart_items,
        subtotal=round(subtotal, 2),
        min_pickup=min_pickup,
        max_pickup=max_pickup,
        slot_options=slot_options,
        is_priority=priority,
    )

@canteen_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    """Adds a dish to the session cart (capped at live stock)."""
    item_id = str(request.form.get('item_id'))
    quantity = int(request.form.get('quantity', 1))

    item = CanteenItem.query.get(int(item_id))
    if not item or not item.is_available or item.stock_quantity <= 0:
        flash("Item is currently unavailable or out of stock.", "danger")
        return redirect(url_for('canteen.index'))

    cart = session.get('canteen_cart', {})
    current_qty = cart.get(item_id, 0)
    cart[item_id] = min(current_qty + quantity, int(item.stock_quantity))
    session['canteen_cart'] = cart

    flash(f"Added {quantity}x {item.name} to your food tray.", "success")
    return redirect(url_for('canteen.index'))

@canteen_bp.route('/cart/update', methods=['POST'])
@login_required
def update_cart_quantity():
    """Phase 6: change the quantity of one cart line (never exceeds stock)."""
    item_id = str(request.form.get('item_id'))
    quantity = request.form.get('quantity', type=int, default=0)

    cart = session.get('canteen_cart', {})
    if quantity is None or quantity <= 0:
        cart.pop(item_id, None)
    else:
        item = CanteenItem.query.get(int(item_id))
        if not item or not item.is_available:
            flash("That item is no longer available.", "warning")
            return redirect(url_for('canteen.cart_view'))
        cart[item_id] = min(quantity, int(item.stock_quantity))
    session['canteen_cart'] = cart
    return redirect(url_for('canteen.cart_view'))

@canteen_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    """Removes an item from cart."""
    cart = session.get('canteen_cart', {})
    cart.pop(str(item_id), None)
    session['canteen_cart'] = cart
    flash("Item removed from cart.", "info")
    return redirect(url_for('canteen.cart_view'))

@canteen_bp.route('/cart/clear', methods=['POST'])
def clear_cart():
    """Empties the cart."""
    session.pop('canteen_cart', None)
    flash("Cart cleared.", "info")
    return redirect(url_for('canteen.index'))

@canteen_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    """
    Phase 6 advance booking with configurable teacher-first slot allocation.
    - Stock and per-slot capacity are validated BEFORE anything is deducted.
    - A rejected checkout never leaves a half-created order or lost stock and
      always names the reason plus the next open slot (nothing silent).
    - Confirmed orders receive an opaque pickup token and a privacy-safe QR.
    """
    user = get_current_user()
    cart = session.get('canteen_cart', {})

    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('canteen.index'))

    cfg = _booking_config()
    payment_method = request.form.get('payment_method', 'upi_simulation')
    is_priority = _is_priority_user(user)

    # ---- Resolve the pickup slot ------------------------------------------
    slot = None
    slot_id = request.form.get('slot_id', type=int)
    if slot_id:
        slot = CanteenPickupSlot.query.get(slot_id)
        if not slot or not slot.is_active or slot.ends_at < datetime.now():
            flash("That pickup slot is no longer open. Please choose another.", "danger")
            return redirect(url_for('canteen.cart_view'))
    else:
        # Legacy clients (no slot chosen): earliest bookable slot if any exist.
        options = booking.bookable_slots(cfg, is_priority)
        slot = options[0]['slot'] if options else None

    if slot:
        availability = booking.slot_availability(slot, cfg, is_priority)
        if not availability['allowed']:
            if availability['reason'] == 'teacher_reserve':
                flash(
                    f"The {slot.name} slot ({slot.slot_date:%d %b}) still has seats held for "
                    f"verified teachers; those seats open to everyone at {slot.start_time}. "
                    "No order was placed and nothing was charged.",
                    "warning",
                )
            else:
                flash(f"The {slot.name} slot ({slot.slot_date:%d %b}) is fully booked. "
                      "No order was placed and nothing was charged.", "warning")
            nxt = booking.next_available_slot(cfg, is_priority, exclude_id=slot.id)
            if nxt:
                flash(f"Next open pickup slot: {nxt.name} on {nxt.slot_date:%d %b} at {nxt.start_time}.", "info")
            else:
                flash("No earlier slot is open right now - please check back after the next period.", "info")
            return redirect(url_for('canteen.cart_view'))
        pickup_time = slot.starts_at
    else:
        # No slots configured at all: original free-datetime behaviour.
        pickup_time_str = request.form.get('pickup_time')
        if pickup_time_str:
            try:
                pickup_time = datetime.strptime(pickup_time_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pickup_time = datetime.now() + timedelta(minutes=20)
        else:
            pickup_time = datetime.now() + timedelta(minutes=20)

    # ---- Validate stock for the WHOLE cart before deducting anything -------
    lines = []
    total_amount = 0.0
    for item_id_str, qty in cart.items():
        item = CanteenItem.query.get(int(item_id_str))
        if not item or not item.is_available:
            flash(f"'{getattr(item, 'name', 'An item')}' is no longer available. "
                  "Your order was not placed.", "danger")
            return redirect(url_for('canteen.cart_view'))
        if item.stock_quantity < qty:
            flash(f"Insufficient stock for '{item.name}' (only {item.stock_quantity} left). "
                  "Your order was not placed and no stock was used.", "danger")
            return redirect(url_for('canteen.cart_view'))
        item_subtotal = float(item.price) * qty
        total_amount += item_subtotal
        lines.append((item, qty, item_subtotal))

    if not lines:
        flash("No valid items in cart.", "danger")
        return redirect(url_for('canteen.index'))

    # ---- Create the order ----------------------------------------------------
    order_timestamp = datetime.utcnow().strftime('%Y%m%d')
    order_code = f"ORD-{order_timestamp}-{random.randint(1000, 9999)}"

    new_order = CanteenOrder(
        order_code=order_code,
        user_id=user.id,
        user_role_at_order=user.role,
        is_priority=is_priority,
        total_amount=total_amount,
        pickup_time=pickup_time,
        slot_id=slot.id if slot else None,
        order_status='pending',
        payment_status='paid' if payment_method != 'cash_at_counter' else 'pending',
        payment_method=payment_method,
    )
    for item, qty, subtotal in lines:
        new_order.items.append(CanteenOrderItem(
            item_id=item.id, item_name=item.name,
            unit_price=item.price, quantity=qty, subtotal=subtotal,
        ))
    db.session.add(new_order)

    # Deduct stock now that every line passed validation
    for item, qty, _ in lines:
        item.stock_quantity -= qty

    # ---- Teacher-first-aware confirmation -------------------------------------
    if cfg['CANTEEN_AUTO_CONFIRM']:
        _confirm_order(new_order, cfg)

    db.session.commit()

    # Realistic pickup estimate (uses final queue position after commit)
    if new_order.order_status in ('pending', 'confirmed') and slot:
        ahead, _total = booking.queue_position(new_order)
        new_order.estimated_ready_at = booking.estimate_ready_at(
            slot, booking.max_prep_minutes(new_order), ahead, cfg)
        db.session.commit()

    # Generate QR Code image on disk (token exists once confirmed)
    if new_order.order_status == 'confirmed':
        qr_path = generate_order_qr(new_order, save_to_disk=True)
        new_order.qr_code_path = qr_path
        db.session.commit()

    # Clear user session cart
    session.pop('canteen_cart', None)

    AuditLog.log(
        action='CANTEEN_ORDER_PLACED',
        module='CANTEEN',
        user_id=user.id,
        details=f"Order {order_code} placed for ₹{total_amount:.2f}. "
                f"Priority: {is_priority}. Slot: {slot.name if slot else 'legacy'}.",
        ip_address=request.remote_addr,
    )

    if new_order.order_status == 'confirmed':
        Notification.notify(
            user.id, "Canteen order confirmed",
            f"Order {order_code} is confirmed for pickup at "
            f"{new_order.estimated_ready_at.strftime('%H:%M') if new_order.estimated_ready_at else pickup_time.strftime('%H:%M')}. "
            "Show your QR code at the counter.",
            category='canteen',
            link_url=url_for('canteen.order_detail', order_code=order_code),
            dedup_key=f"canteen:{new_order.id}:confirmed",
        )
        db.session.commit()

    if is_priority:
        flash("Order placed successfully with TEACHER-FIRST PRIORITY allocation!", "success")
    elif user.role == 'teacher' and not user.is_verified:
        flash("Order placed successfully! Note: Your teacher account is awaiting Main Admin verification; priority queueing will activate once verified.", "info")
    else:
        flash("Order placed successfully! Present your QR code at the counter during pickup.", "success")

    return redirect(url_for('canteen.order_detail', order_code=order_code))

def _confirm_order(order, cfg):
    """Phase 6 confirmation: timestamp, opaque pickup token, notification."""
    order.order_status = 'confirmed'
    order.confirmed_at = datetime.utcnow()
    if not order.pickup_token:
        order.pickup_token = secrets.token_urlsafe(24)

@canteen_bp.route('/order/<order_code>')
@login_required
def order_detail(order_code):
    """Order confirmation and QR pickup display."""
    user = get_current_user()
    order = CanteenOrder.query.filter_by(order_code=order_code).first_or_404()

    # Authorization check
    if order.user_id != user.id and user.role not in ['main_admin', 'canteen_admin']:
        flash("Unauthorized to view this order.", "danger")
        return redirect(url_for('canteen.index'))

    return render_template('canteen/order_success.html', user=user, order=order)

@canteen_bp.route('/my-orders')
@login_required
def my_orders():
    """List of all orders placed by the current user."""
    user = get_current_user()
    orders = CanteenOrder.query.filter_by(user_id=user.id).order_by(CanteenOrder.created_at.desc()).all()
    return render_template('canteen/my_orders.html', user=user, orders=orders)

@canteen_bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel a not-yet-cooked order; stock is returned and payment refunded."""
    user = get_current_user()
    order = CanteenOrder.query.get_or_404(order_id)

    if order.user_id != user.id and user.role not in ['main_admin', 'canteen_admin']:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('canteen.my_orders'))

    if order.order_status not in booking.PENDING + ('confirmed',):
        flash("Orders that are already being prepared or served cannot be cancelled - "
              "use 'Request Refund' instead.", "warning")
        return redirect(url_for('canteen.order_detail', order_code=order.order_code))

    # Restore stock
    for item in order.items:
        canteen_item = CanteenItem.query.get(item.item_id)
        if canteen_item:
            canteen_item.stock_quantity += item.quantity

    order.order_status = 'cancelled'
    order.payment_status = 'refunded'
    order.refund_reason = request.form.get('refund_reason', 'Cancelled by customer before preparation')
    db.session.commit()

    Notification.notify(
        order.user_id, "Canteen order cancelled",
        f"Order {order.order_code} was cancelled and ₹{order.total_amount} will be "
        "returned to the original payment method.",
        category='canteen',
        link_url=url_for('canteen.order_detail', order_code=order.order_code),
        dedup_key=f"canteen:{order.id}:cancelled",
    )
    db.session.commit()

    flash(f"Order #{order.order_code} cancelled. Simulated refund of ₹{order.total_amount} initiated to original payment source.", "info")
    return redirect(url_for('canteen.my_orders'))

@canteen_bp.route('/order/<int:order_id>/request-refund', methods=['POST'])
@login_required
def request_refund(order_id):
    """
    Phase 6: refund request for orders already in the kitchen pipeline
    (preparing/ready). The canteen admin then moves it through
    Refund Processing -> Refunded. Never silently drops the order.
    """
    user = get_current_user()
    order = CanteenOrder.query.get_or_404(order_id)

    if order.user_id != user.id:
        flash("You can only request refunds for your own orders.", "danger")
        return redirect(url_for('canteen.my_orders'))

    if order.order_status not in ('confirmed', 'preparing', 'ready'):
        flash("This order cannot be refunded right now - use Cancel if it is still pending.", "warning")
        return redirect(url_for('canteen.order_detail', order_code=order.order_code))

    order.order_status = 'refund_requested'
    order.refund_reason = (request.form.get('refund_reason') or 'Refund requested by customer').strip()[:500]
    db.session.commit()

    Notification.notify(
        order.user_id, "Refund requested",
        f"We received your refund request for order {order.order_code}. "
        "The canteen team will process it shortly.",
        category='canteen',
        link_url=url_for('canteen.order_detail', order_code=order.order_code),
        dedup_key=f"canteen:{order.id}:refund_requested",
    )
    db.session.commit()

    AuditLog.log(action='CANTEEN_REFUND_REQUESTED', module='CANTEEN', user_id=user.id,
                 details=f"Order {order.order_code}: {order.refund_reason}",
                 ip_address=request.remote_addr)

    flash(f"Refund requested for order #{order.order_code}. You will be notified when it is processed.", "info")
    return redirect(url_for('canteen.order_detail', order_code=order.order_code))
