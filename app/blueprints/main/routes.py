from datetime import datetime, time

from flask import render_template, current_app
from sqlalchemy import func, desc

from app.blueprints.main import main_bp
from app.database import db
from app.models import (
    NavigationNode, LostFoundItem, LostFoundClaim,
    CanteenItem, CanteenOrder, CanteenOrderItem, User,
)
from app.utils.auth_helpers import get_current_user


@main_bp.route('/')
def index():
    """Unified landing portal / dashboard for Smart Campus 360.

    Phase 5 dashboard redesign: this view aggregates real, read-only data from every
    module to feed the glassmorphism panels. No business logic is changed - the
    queries below only COUNT / SELECT existing records, so the dashboard never shows
    fabricated numbers. Where the reference mock-up used placeholder content (e.g. the
    events timeline) we render genuine recent activity instead.
    """
    current_user = get_current_user()
    day_start = datetime.combine(datetime.today(), time.min)

    # --- Core aggregate statistics across the integrated modules (live DB data) ---
    classrooms_count = NavigationNode.query.filter_by(category='Classroom').count()
    labs_count = NavigationNode.query.filter(
        NavigationNode.category.like('%Lab%')
    ).count()

    stats = {
        # Existing keys preserved (used elsewhere / tests)
        "nodes_count": NavigationNode.query.count(),
        "open_lost_found": LostFoundItem.query.filter_by(status='open').count(),
        "menu_items_count": CanteenItem.query.filter_by(is_available=True).count(),
        "active_orders_count": CanteenOrder.query.filter(
            CanteenOrder.order_status.in_(['placed', 'preparing', 'ready'])
        ).count(),
        # Welcome-section people / place metrics
        "students_count": User.query.filter_by(role='student', is_active=True).count(),
        "faculty_count": User.query.filter(User.role == 'teacher').count(),
        "classrooms_count": classrooms_count,
        "rooms_labs": classrooms_count + labs_count,
        "buildings_count": db.session.query(
            func.count(func.distinct(NavigationNode.building))
        ).scalar() or 0,
        # Lost & Found reporting stats
        "lf_total": LostFoundItem.query.count(),
        "lf_lost": LostFoundItem.query.filter_by(report_type='lost').count(),
        "lf_found": LostFoundItem.query.filter_by(report_type='found').count(),
        "lf_resolved": LostFoundItem.query.filter_by(status='closed').count(),
        "pending_claims": LostFoundClaim.query.filter_by(status='pending').count(),
        # Canteen booking stats
        "orders_total": CanteenOrder.query.count(),
        "orders_today": CanteenOrder.query.filter(CanteenOrder.created_at >= day_start).count(),
        "orders_ready": CanteenOrder.query.filter_by(order_status='ready').count(),
    }

    # --- Recent Lost & Found activity (newest first) ---
    recent_lost_found = (
        LostFoundItem.query.order_by(desc(LostFoundItem.created_at)).limit(6).all()
    )

    # --- Popular canteen items by units sold (falls back to live menu if no sales) ---
    sold_rows = (
        db.session.query(
            CanteenOrderItem.item_id,
            func.sum(CanteenOrderItem.quantity).label('qty'),
        )
        .group_by(CanteenOrderItem.item_id)
        .order_by(desc('qty'))
        .limit(5)
        .all()
    )
    popular_items = []
    for row in sold_rows:
        item = CanteenItem.query.get(row.item_id)
        if item:
            popular_items.append({"item": item, "sold": int(row.qty or 0)})
    if not popular_items:  # real menu preview when there are no orders yet
        for item in CanteenItem.query.filter_by(is_available=True).limit(5).all():
            popular_items.append({"item": item, "sold": 0})

    # --- Today's live snapshot (derived from real records, never invented events) ---
    todays_stats = {
        "orders_today": stats["orders_today"],
        "reports_today": LostFoundItem.query.filter(
            LostFoundItem.created_at >= day_start
        ).count(),
        "returns_today": LostFoundItem.query.filter(
            LostFoundItem.collected_at >= day_start
        ).count(),
        "ready_now": stats["orders_ready"],
        "priority_today": CanteenOrder.query.filter(
            CanteenOrder.created_at >= day_start, CanteenOrder.is_priority.is_(True)
        ).count(),
    }

    # --- Activity timeline: genuine recent records (orders + reports), newest first ---
    timeline = []
    for order in CanteenOrder.query.order_by(desc(CanteenOrder.created_at)).limit(4).all():
        who = order.customer.full_name if order.customer else "Campus"
        timeline.append({
            "ts": order.created_at,
            "time": order.created_at.strftime('%I:%M %p') if order.created_at else '',
            "title": f"Order {order.order_code} placed",
            "place": f"{who} - {'Priority' if order.is_priority else 'Standard'}",
            "color": "amber",
        })
    for it in recent_lost_found[:4]:
        timeline.append({
            "ts": it.created_at,
            "time": it.created_at.strftime('%I:%M %p') if it.created_at else '',
            "title": f"{it.report_type.capitalize()} item reported",
            "place": f"{it.title} - {it.location_reported}",
            "color": "rose" if it.report_type == 'lost' else "green",
        })
    timeline.sort(key=lambda e: e["ts"] or datetime.min, reverse=True)
    today_events = timeline[:5]

    # --- Quick Location Finder source list (real campus nodes) ---
    quick_locations = (
        db.session.query(
            NavigationNode.id, NavigationNode.name,
            NavigationNode.building, NavigationNode.category,
        )
        .order_by(NavigationNode.building.asc(), NavigationNode.name.asc())
        .all()
    )
    quick_locations = [
        {"id": n.id, "name": n.name, "building": n.building, "category": n.category}
        for n in quick_locations
    ]

    return render_template(
        'main/index.html',
        user=current_user,
        stats=stats,
        recent_lost_found=recent_lost_found,
        popular_items=popular_items,
        todays_stats=todays_stats,
        today_events=today_events,
        quick_locations=quick_locations,
    )


@main_bp.route('/about')
def about():
    """Information regarding GEC Mosalehosahalli, system architecture, and module documentation."""
    current_user = get_current_user()
    return render_template('main/about.html', user=current_user)
