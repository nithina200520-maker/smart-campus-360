from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from app.blueprints.canteen_admin import canteen_admin_bp
from app.models import CanteenOrder, CanteenItem, CanteenCategory, AuditLog
from app.database import db
from app.utils.auth_helpers import role_required, get_current_user

@canteen_admin_bp.route('/dashboard')
@role_required(['canteen_admin', 'main_admin'])
def dashboard():
    """
    Canteen Operator Command Center:
    Orders queue with strict Teacher-First Priority sorting,
    preparation controls, and inventory overview.
    """
    user = get_current_user()

    # Priority sorting: Teachers (is_priority=True) first, then by earliest pickup time
    active_orders = (
        CanteenOrder.query
        .filter(CanteenOrder.order_status.in_(['placed', 'preparing', 'ready']))
        .order_by(CanteenOrder.is_priority.desc(), CanteenOrder.pickup_time.asc())
        .all()
    )

    recent_completed = (
        CanteenOrder.query
        .filter(CanteenOrder.order_status.in_(['collected', 'cancelled', 'refunded']))
        .order_by(CanteenOrder.updated_at.desc())
        .limit(10)
        .all()
    )

    total_items = CanteenItem.query.count()
    low_stock_items = CanteenItem.query.filter(CanteenItem.stock_quantity < 10).all()
    
    # Financial aggregate
    total_sales = db.session.query(db.func.sum(CanteenOrder.total_amount)).filter_by(payment_status='paid').scalar() or 0.0

    return render_template(
        'canteen_admin/dashboard.html',
        user=user,
        active_orders=active_orders,
        recent_completed=recent_completed,
        total_items=total_items,
        low_stock_items=low_stock_items,
        total_sales=float(total_sales)
    )

@canteen_admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def update_order_status(order_id):
    """Transition order status: placed -> preparing -> ready -> collected."""
    order = CanteenOrder.query.get_or_404(order_id)
    new_status = request.form.get('new_status')

    valid_statuses = ['placed', 'preparing', 'ready', 'collected', 'cancelled', 'refunded']
    if new_status in valid_statuses:
        order.order_status = new_status
        if new_status == 'collected':
            order.collected_at = datetime.utcnow()
        elif new_status == 'refunded':
            order.payment_status = 'refunded'
            order.refund_reason = request.form.get('refund_reason', 'Canteen cancellation refund processed')

        db.session.commit()
        flash(f"Order #{order.order_code} status updated to {new_status.upper()}.", "success")
    else:
        flash("Invalid order status transition.", "danger")

    return redirect(url_for('canteen_admin.dashboard'))

@canteen_admin_bp.route('/verify-pickup', methods=['POST'])
@role_required(['canteen_admin', 'main_admin'])
def verify_pickup():
    """Verify pickup by order code (entered manually or scanned via QR code reader)."""
    order_code = request.form.get('order_code', '').strip().upper()
    order = CanteenOrder.query.filter_by(order_code=order_code).first()

    if not order:
        flash(f"No order found with code '{order_code}'.", "danger")
        return redirect(url_for('canteen_admin.dashboard'))

    if order.order_status == 'collected':
        flash(f"Order #{order.order_code} was ALREADY COLLECTED at {order.collected_at}.", "warning")
        return redirect(url_for('canteen_admin.dashboard'))

    order.order_status = 'collected'
    order.collected_at = datetime.utcnow()
    db.session.commit()

    flash(f"Success! Order #{order.order_code} verified and marked COLLECTED for {order.customer.full_name} ({order.user_role_at_order.title()}).", "success")
    return redirect(url_for('canteen_admin.dashboard'))

@canteen_admin_bp.route('/menu', methods=['GET', 'POST'])
@role_required(['canteen_admin', 'main_admin'])
def menu_manage():
    """Manage canteen menu items and stock availability."""
    user = get_current_user()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_item':
            name = request.form.get('name', '').strip()
            category_id = int(request.form.get('category_id'))
            price = float(request.form.get('price', 0.0))
            stock = int(request.form.get('stock_quantity', 50))
            description = request.form.get('description', '')

            item = CanteenItem(
                name=name,
                category_id=category_id,
                price=price,
                stock_quantity=stock,
                description=description,
                is_available=True
            )
            db.session.add(item)
            db.session.commit()
            flash(f"Item '{name}' added to menu.", "success")
            return redirect(url_for('canteen_admin.menu_manage'))

    items = CanteenItem.query.order_by(CanteenItem.category_id.asc(), CanteenItem.name.asc()).all()
    categories = CanteenCategory.query.order_by(CanteenCategory.display_order.asc()).all()

    return render_template('canteen_admin/menu_manage.html', user=user, items=items, categories=categories)

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
