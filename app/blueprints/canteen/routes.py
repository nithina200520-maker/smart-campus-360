from datetime import datetime, timedelta
import random
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from app.blueprints.canteen import canteen_bp
from app.models import CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem, AuditLog
from app.database import db
from app.utils.auth_helpers import login_required, get_current_user
from app.utils.qr_generator import generate_order_qr

@canteen_bp.route('/')
def index():
    """Module 3: Smart Canteen Menu and Booking foundation."""
    user = get_current_user()
    categories = CanteenCategory.query.filter_by(is_active=True).order_by(CanteenCategory.display_order.asc()).all()
    cart = session.get('canteen_cart', {})
    cart_total_count = sum(cart.values())

    return render_template(
        'canteen/index.html',
        user=user,
        categories=categories,
        cart=cart,
        cart_total_count=cart_total_count
    )

@canteen_bp.route('/cart')
@login_required
def cart_view():
    """Shopping cart and advance pickup scheduler."""
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

    # Earliest pickup is 15 minutes from now
    min_pickup = (datetime.now() + timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M')
    max_pickup = (datetime.now() + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M')

    return render_template(
        'canteen/cart.html',
        user=user,
        cart_items=cart_items,
        subtotal=round(subtotal, 2),
        min_pickup=min_pickup,
        max_pickup=max_pickup
    )

@canteen_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    """Adds a dish to the session cart."""
    item_id = str(request.form.get('item_id'))
    quantity = int(request.form.get('quantity', 1))

    item = CanteenItem.query.get(int(item_id))
    if not item or not item.is_available or item.stock_quantity <= 0:
        flash("Item is currently unavailable or out of stock.", "danger")
        return redirect(url_for('canteen.index'))

    cart = session.get('canteen_cart', {})
    current_qty = cart.get(item_id, 0)
    cart[item_id] = current_qty + quantity
    session['canteen_cart'] = cart

    flash(f"Added {quantity}x {item.name} to your food tray.", "success")
    return redirect(url_for('canteen.index'))

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
    Submits advance canteen order.
    Enforces Teacher-First Priority queue handling:
    If customer has role 'teacher', 'is_priority' is automatically set to True!
    Generates QR code for pickup verification.
    """
    user = get_current_user()
    cart = session.get('canteen_cart', {})

    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('canteen.index'))

    pickup_time_str = request.form.get('pickup_time')
    payment_method = request.form.get('payment_method', 'upi_simulation')

    if pickup_time_str:
        try:
            pickup_time = datetime.strptime(pickup_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            pickup_time = datetime.utcnow() + timedelta(minutes=20)
    else:
        pickup_time = datetime.utcnow() + timedelta(minutes=20)

    # Determine priority status: Teacher-First Order Priority granted ONLY to verified teachers
    is_teacher_order = bool(user.role == 'teacher' and user.is_verified)

    # Generate unique order tracking code
    order_timestamp = datetime.utcnow().strftime('%Y%m%d')
    random_suffix = random.randint(1000, 9999)
    order_code = f"ORD-{order_timestamp}-{random_suffix}"

    # Calculate totals and verify stock
    total_amount = 0.0
    order_items_to_add = []

    for item_id_str, qty in cart.items():
        item = CanteenItem.query.get(int(item_id_str))
        if not item or not item.is_available:
            continue
        
        # Deduct stock
        if item.stock_quantity >= qty:
            item.stock_quantity -= qty
        else:
            flash(f"Insufficient stock for '{item.name}'. Order could not be finalized.", "danger")
            return redirect(url_for('canteen.cart_view'))

        item_subtotal = float(item.price) * qty
        total_amount += item_subtotal

        order_item = CanteenOrderItem(
            item_id=item.id,
            item_name=item.name,
            unit_price=item.price,
            quantity=qty,
            subtotal=item_subtotal
        )
        order_items_to_add.append(order_item)

    if not order_items_to_add:
        flash("No valid items in cart.", "danger")
        return redirect(url_for('canteen.index'))

    new_order = CanteenOrder(
        order_code=order_code,
        user_id=user.id,
        user_role_at_order=user.role,
        is_priority=is_teacher_order,
        total_amount=total_amount,
        pickup_time=pickup_time,
        order_status='placed',
        payment_status='paid',
        payment_method=payment_method
    )
    new_order.items = order_items_to_add
    db.session.add(new_order)
    db.session.commit()

    # Generate QR Code image on disk
    qr_path = generate_order_qr(new_order, save_to_disk=True)
    new_order.qr_code_path = qr_path
    db.session.commit()

    # Clear user session cart
    session.pop('canteen_cart', None)

    # Log audit
    audit = AuditLog(
        user_id=user.id,
        action='CANTEEN_ORDER_PLACED',
        module='CANTEEN',
        details=f"Order {order_code} placed for ₹{total_amount:.2f}. Priority: {is_teacher_order}",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    if is_teacher_order:
        flash("Order placed successfully with TEACHER-FIRST PRIORITY status!", "success")
    elif user.role == 'teacher' and not user.is_verified:
        flash("Order placed successfully! Note: Your teacher account is awaiting Main Admin verification; priority queueing will activate once verified.", "info")
    else:
        flash("Order placed successfully! Present your QR code at the counter during pickup.", "success")

    return redirect(url_for('canteen.order_detail', order_code=order_code))

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
    """Cancel order and initiate simulated refund."""
    user = get_current_user()
    order = CanteenOrder.query.get_or_404(order_id)

    if order.user_id != user.id and user.role not in ['main_admin', 'canteen_admin']:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('canteen.my_orders'))

    if order.order_status in ['ready', 'collected']:
        flash("Orders that are already prepared or collected cannot be cancelled.", "warning")
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

    flash(f"Order #{order.order_code} cancelled. Simulated refund of ₹{order.total_amount} initiated to original payment source.", "info")
    return redirect(url_for('canteen.my_orders'))
