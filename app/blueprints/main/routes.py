from flask import render_template, current_app
from app.blueprints.main import main_bp
from app.models import NavigationNode, LostFoundItem, CanteenItem, CanteenOrder, User
from app.utils.auth_helpers import get_current_user

@main_bp.route('/')
def index():
    """Unified landing portal linking all 3 modules and showcasing GEC Mosalehosahalli."""
    current_user = get_current_user()

    # High-level aggregate statistics across the integrated modules
    stats = {
        "nodes_count": NavigationNode.query.count(),
        "open_lost_found": LostFoundItem.query.filter_by(status='open').count(),
        "menu_items_count": CanteenItem.query.filter_by(is_available=True).count(),
        "active_orders_count": CanteenOrder.query.filter(CanteenOrder.order_status.in_(['placed', 'preparing', 'ready'])).count()
    }

    return render_template('main/index.html', user=current_user, stats=stats)

@main_bp.route('/about')
def about():
    """Information regarding GEC Mosalehosahalli, system architecture, and module documentation."""
    current_user = get_current_user()
    return render_template('main/about.html', user=current_user)
