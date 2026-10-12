import csv
import io
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, current_app, Response
from app.blueprints.admin import admin_bp
from app.models import User, NavigationNode, NavigationEdge, CampusFloorPlan, LostFoundItem, CanteenItem, CanteenOrder, AuditLog
from app.database import db
from app.utils.auth_helpers import role_required, get_current_user

ALLOWED_PHOTO_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

NODE_CSV_TEMPLATE = """node_code,name,building,floor,category,description,x_coord,y_coord,photo_url,is_panoramic,is_accessible,is_sample_data
NODE_EXAMPLE_1,Sample Classroom 101,Academic Block A,Ground Floor,Classroom,Imported via Phase 3 template,420,300,,False,True,True
NODE_EXAMPLE_2,Sample Corridor A,Academic Block A,Ground Floor,Corridor,Corridor connecting rooms,360,300,/static/uploads/navigation/corridor.jpg,False,True,True
"""

EDGE_CSV_TEMPLATE = """source_node_code,target_node_code,distance_meters,direction_hint,is_bidirectional,is_sample_data
NODE_EXAMPLE_1,NODE_EXAMPLE_2,15,Walk straight along the corridor,True,True
"""

FLOORPLAN_CSV_TEMPLATE = """building,floor,title,image_url,is_sample_data
Academic Block A,Ground Floor,Block A Ground Floor Plan,/static/uploads/navigation/block_a_gf_plan.png,True
"""

def _save_navigation_photo(file):
    """Stores an uploaded navigation photograph under static/uploads/navigation and returns its web URL."""
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_PHOTO_EXT:
        return None
    filename = secure_filename(f"nav_{int(datetime.utcnow().timestamp())}_{file.filename}")
    upload_dir = Path(current_app.root_path) / "static" / "uploads" / "navigation"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file.save(upload_dir / filename)
    return f"/static/uploads/navigation/{filename}"

@admin_bp.route('/dashboard')
@role_required('main_admin')
def dashboard():
    """Main Admin master command center controlling all 3 modules."""
    user = get_current_user()

    total_users = User.query.count()
    pending_teachers_count = User.query.filter_by(role='teacher', is_verified=False).count()
    total_nodes = NavigationNode.query.count()
    total_edges = NavigationEdge.query.count()
    total_lf_items = LostFoundItem.query.count()
    open_lf_items = LostFoundItem.query.filter_by(status='open').count()
    total_orders = CanteenOrder.query.count()
    total_revenue = db.session.query(db.func.sum(CanteenOrder.total_amount)).filter_by(payment_status='paid').scalar() or 0.0

    recent_audits = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(6).all()
    pending_teachers = User.query.filter_by(role='teacher', is_verified=False).limit(5).all()

    stats = {
        "total_users": total_users,
        "pending_teachers_count": pending_teachers_count,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "total_lf_items": total_lf_items,
        "open_lf_items": open_lf_items,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue)
    }

    return render_template(
        'admin/dashboard.html',
        user=user,
        stats=stats,
        recent_audits=recent_audits,
        recent_users=recent_users,
        pending_teachers=pending_teachers
    )

@admin_bp.route('/users')
@role_required('main_admin')
def users_list():
    """User account management table with role assignment and verification filters."""
    user = get_current_user()
    role_filter = request.args.get('role')
    status_filter = request.args.get('status')
    pending_only = request.args.get('pending') == '1'

    query = User.query.order_by(User.created_at.desc())

    if role_filter:
        query = query.filter_by(role=role_filter)

    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)

    if pending_only:
        query = query.filter_by(role='teacher', is_verified=False)

    users = query.all()
    pending_teachers_count = User.query.filter_by(role='teacher', is_verified=False).count()

    return render_template(
        'admin/users.html',
        user=user,
        users=users,
        pending_teachers_count=pending_teachers_count,
        current_role=role_filter,
        current_status=status_filter,
        pending_only=pending_only
    )

@admin_bp.route('/users/<int:user_id>/verify-teacher', methods=['POST'])
@role_required('main_admin')
def verify_teacher(user_id):
    """Verifies a teacher account, unlocking Teacher-First Priority queue status."""
    admin_user = get_current_user()
    target_user = User.query.get_or_404(user_id)

    if target_user.role != 'teacher':
        flash("Target user is not a teacher account.", "warning")
        return redirect(url_for('admin.users_list'))

    target_user.is_verified = True
    db.session.commit()

    AuditLog.log(
        action='TEACHER_VERIFIED',
        module='ADMIN',
        user_id=target_user.id,
        details=f"Main Admin '{admin_user.full_name}' verified faculty credentials for '{target_user.full_name}' (Emp ID: {target_user.usn_or_emp_id}). Priority queue active.",
        ip_address=request.remote_addr
    )

    flash(f"Success! Faculty credentials approved for {target_user.full_name}. Teacher-First Priority queue is now UNLOCKED.", "success")
    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.route('/users/<int:user_id>/revoke-teacher', methods=['POST'])
@role_required('main_admin')
def revoke_teacher(user_id):
    """Revokes teacher verification status, resetting to standard queue."""
    admin_user = get_current_user()
    target_user = User.query.get_or_404(user_id)

    target_user.is_verified = False
    db.session.commit()

    AuditLog.log(
        action='TEACHER_VERIFICATION_REVOKED',
        module='ADMIN',
        user_id=target_user.id,
        details=f"Main Admin '{admin_user.full_name}' revoked teacher verification for '{target_user.full_name}'.",
        ip_address=request.remote_addr
    )

    flash(f"Teacher verification revoked for {target_user.full_name}. Reverted to standard queue.", "warning")
    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@role_required('main_admin')
def toggle_user_status(user_id):
    """Toggle active/suspended status for a user."""
    admin_user = get_current_user()
    target_user = User.query.get_or_404(user_id)

    if target_user.role == 'main_admin':
        flash("Cannot suspend Main Admin accounts.", "danger")
        return redirect(url_for('admin.users_list'))

    target_user.is_active = not target_user.is_active
    db.session.commit()

    action = "activated" if target_user.is_active else "suspended"
    action_type = "USER_ACTIVATED" if target_user.is_active else "USER_DEACTIVATED"

    AuditLog.log(
        action=action_type,
        module='ADMIN',
        user_id=target_user.id,
        details=f"Main Admin '{admin_user.full_name}' {action} account '{target_user.email}'.",
        ip_address=request.remote_addr
    )

    flash(f"Account for {target_user.full_name} has been {action}.", "success")
    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.route('/users/<int:user_id>/change-role', methods=['POST'])
@role_required('main_admin')
def change_user_role(user_id):
    """Modify role for a user."""
    admin_user = get_current_user()
    target_user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    
    if new_role in ['main_admin', 'canteen_admin', 'teacher', 'student', 'visitor']:
        old_role = target_user.role
        target_user.role = new_role
        # If changing to teacher, set verified to False unless already verified
        if new_role == 'teacher' and old_role != 'teacher':
            target_user.is_verified = False
        db.session.commit()

        AuditLog.log(
            action='USER_ROLE_CHANGED',
            module='ADMIN',
            user_id=target_user.id,
            details=f"Main Admin '{admin_user.full_name}' changed role of '{target_user.email}' from {old_role} to {new_role}.",
            ip_address=request.remote_addr
        )

        flash(f"Role updated from {old_role} to {new_role} for {target_user.full_name}.", "success")
    else:
        flash("Invalid role specified.", "danger")

    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.route('/create-canteen-admin', methods=['GET', 'POST'])
@role_required('main_admin')
def create_canteen_admin():
    """Main Admin capability to create dedicated Canteen Admin accounts."""
    admin_user = get_current_user()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        department = request.form.get('department', 'Campus Dining & Canteen Operations').strip()
        phone = request.form.get('phone', '').strip()

        if not full_name or not email or not password:
            flash("All fields are required to provision a Canteen Admin.", "warning")
            return render_template('admin/create_canteen_admin.html', user=admin_user)

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return render_template('admin/create_canteen_admin.html', user=admin_user)

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash(f"An account with email '{email}' already exists.", "danger")
            return render_template('admin/create_canteen_admin.html', user=admin_user)

        canteen_admin = User(
            full_name=full_name,
            email=email,
            role='canteen_admin',
            department=department,
            phone=phone,
            is_verified=True,
            is_active=True
        )
        canteen_admin.set_password(password)
        db.session.add(canteen_admin)
        db.session.commit()

        AuditLog.log(
            action='CANTEEN_ADMIN_CREATED',
            module='ADMIN',
            user_id=canteen_admin.id,
            details=f"Main Admin '{admin_user.full_name}' provisioned Canteen Admin '{canteen_admin.email}'.",
            ip_address=request.remote_addr
        )

        flash(f"Canteen Admin account successfully created for '{full_name}' ({email})!", "success")
        return redirect(url_for('admin.users_list'))

    return render_template('admin/create_canteen_admin.html', user=admin_user)

@admin_bp.route('/audit-logs')
@role_required('main_admin')
def audit_logs():
    """Comprehensive searchable security and administrative audit log viewer."""
    user = get_current_user()
    module_filter = request.args.get('module')
    search_q = request.args.get('q', '').strip()

    query = AuditLog.query.order_by(AuditLog.created_at.desc())

    if module_filter:
        query = query.filter_by(module=module_filter)

    if search_q:
        query = query.filter(
            (AuditLog.action.ilike(f"%{search_q}%")) |
            (AuditLog.details.ilike(f"%{search_q}%"))
        )

    logs = query.limit(100).all()

    return render_template(
        'admin/audit_logs.html',
        user=user,
        logs=logs,
        current_module=module_filter,
        search_query=search_q
    )

# ---------------------------------------------------------------------------
# PHASE 3: SMART CAMPUS NAVIGATION - MAP, NODE, EDGE, FLOOR PLAN MANAGEMENT
# ---------------------------------------------------------------------------

@admin_bp.route('/navigation/manage')
@role_required('main_admin')
def manage_navigation():
    """Main Admin map manager: buildings, floors, rooms, navigation points, photos and paths."""
    user = get_current_user()
    nodes = NavigationNode.query.order_by(NavigationNode.building.asc(), NavigationNode.floor.asc(), NavigationNode.name.asc()).all()
    edges = NavigationEdge.query.order_by(NavigationEdge.id.asc()).all()
    floor_plans = CampusFloorPlan.query.order_by(CampusFloorPlan.building.asc()).all()
    buildings = sorted(list(set(n.building for n in nodes)))

    return render_template(
        'admin/manage_navigation.html',
        user=user,
        nodes=nodes,
        edges=edges,
        floor_plans=floor_plans,
        buildings=buildings
    )

@admin_bp.route('/navigation/node/create', methods=['POST'])
@role_required('main_admin')
def create_nav_node():
    """Adds a navigation point (classroom, lab, HOD office, corridor, staircase...) with optional photo."""
    user = get_current_user()
    node_code = request.form.get('node_code', '').strip().upper()
    name = request.form.get('name', '').strip()
    building = request.form.get('building', '').strip()
    floor = request.form.get('floor', 'Ground Floor').strip()
    category = request.form.get('category', 'Classroom').strip()

    if not node_code or not name or not building:
        flash("Node code, name and building are required.", "danger")
        return redirect(url_for('admin.manage_navigation'))
    if NavigationNode.query.filter_by(node_code=node_code).first():
        flash(f"Node code '{node_code}' already exists. Choose a unique code.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    photo_file = request.files.get('photo')
    photo_url = request.form.get('photo_url', '').strip() or None
    if photo_file and photo_file.filename:
        photo_url = _save_navigation_photo(photo_file) or photo_url

    node = NavigationNode(
        node_code=node_code,
        name=name,
        building=building,
        floor=floor,
        category=category,
        description=request.form.get('description', '').strip(),
        x_coord=int(request.form.get('x_coord') or 0),
        y_coord=int(request.form.get('y_coord') or 0),
        photo_url=photo_url,
        is_panoramic=bool(request.form.get('is_panoramic')),
        is_accessible=bool(request.form.get('is_accessible', 'on')),
        is_sample_data=bool(request.form.get('is_sample_data'))
    )
    db.session.add(node)
    db.session.commit()
    AuditLog.log(action='NAV_NODE_CREATED', module='NAVIGATION', user_id=user.id,
                 details=f"Created navigation node {node_code}: '{name}' ({building}, {floor}).", ip_address=request.remote_addr)
    flash(f"Navigation point '{name}' created.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/node/<int:node_id>/delete', methods=['POST'])
@role_required('main_admin')
def delete_nav_node(node_id):
    node = NavigationNode.query.get_or_404(node_id)
    code, name = node.node_code, node.name
    db.session.delete(node)
    db.session.commit()
    AuditLog.log(action='NAV_NODE_DELETED', module='NAVIGATION', user_id=get_current_user().id,
                 details=f"Deleted navigation node {code}: '{name}'.", ip_address=request.remote_addr)
    flash(f"Navigation point '{name}' deleted along with its connections.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/edge/create', methods=['POST'])
@role_required('main_admin')
def create_nav_edge():
    """Defines a walkable connection between two navigation points."""
    source_id = request.form.get('source_node_id', type=int)
    target_id = request.form.get('target_node_id', type=int)
    distance = request.form.get('distance_meters', 15.0, type=float)
    hint = request.form.get('direction_hint', '').strip()
    bidirectional = bool(request.form.get('is_bidirectional'))

    if not source_id or not target_id or source_id == target_id:
        flash("Select two different points to connect.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    source = NavigationNode.query.get(source_id)
    target = NavigationNode.query.get(target_id)
    if not source or not target:
        flash("Unknown node selected.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    exists = NavigationEdge.query.filter_by(source_node_id=source_id, target_node_id=target_id).first()
    if exists:
        flash(f"A path from '{source.name}' to '{target.name}' already exists.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    edge = NavigationEdge(
        source_node_id=source_id, target_node_id=target_id,
        distance_meters=max(0.5, distance), direction_hint=hint or None,
        is_bidirectional=bidirectional,
        is_sample_data=bool(request.form.get('is_sample_data'))
    )
    db.session.add(edge)
    db.session.commit()
    AuditLog.log(action='NAV_EDGE_CREATED', module='NAVIGATION', user_id=get_current_user().id,
                 details=f"Connected '{source.name}' -> '{target.name}' ({distance}m).", ip_address=request.remote_addr)
    flash("Walkable path saved.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/edge/<int:edge_id>/delete', methods=['POST'])
@role_required('main_admin')
def delete_nav_edge(edge_id):
    edge = NavigationEdge.query.get_or_404(edge_id)
    db.session.delete(edge)
    db.session.commit()
    AuditLog.log(action='NAV_EDGE_DELETED', module='NAVIGATION', user_id=get_current_user().id,
                 details=f"Removed walkable path #{edge_id}.", ip_address=request.remote_addr)
    flash("Path connection removed.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/floorplan/create', methods=['POST'])
@role_required('main_admin')
def create_floor_plan():
    """Main Admin uploads a digital floor plan image for a building/floor."""
    building = request.form.get('building', '').strip()
    floor = request.form.get('floor', 'Ground Floor').strip()
    title = request.form.get('title', '').strip()

    if not building or not title:
        flash("Building and title are required for a floor plan.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    image_url = request.form.get('image_url', '').strip() or None
    plan_file = request.files.get('plan_image')
    if plan_file and plan_file.filename:
        image_url = _save_navigation_photo(plan_file) or image_url

    plan = CampusFloorPlan(
        building=building, floor=floor, title=title,
        image_url=image_url,
        is_sample_data=bool(request.form.get('is_sample_data'))
    )
    db.session.add(plan)
    db.session.commit()
    AuditLog.log(action='NAV_FLOORPLAN_UPLOADED', module='NAVIGATION', user_id=get_current_user().id,
                 details=f"Uploaded floor plan '{title}' for {building} ({floor}).", ip_address=request.remote_addr)
    flash(f"Floor plan '{title}' saved.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/floorplan/<int:plan_id>/delete', methods=['POST'])
@role_required('main_admin')
def delete_floor_plan(plan_id):
    plan = CampusFloorPlan.query.get_or_404(plan_id)
    title = plan.title
    db.session.delete(plan)
    db.session.commit()
    AuditLog.log(action='NAV_FLOORPLAN_DELETED', module='NAVIGATION', user_id=get_current_user().id,
                 details=f"Deleted floor plan '{title}'.", ip_address=request.remote_addr)
    flash(f"Floor plan '{title}' deleted.", "success")
    return redirect(url_for('admin.manage_navigation'))

@admin_bp.route('/navigation/template/<kind>')
@role_required('main_admin')
def download_import_template(kind):
    """Serves CSV import templates for nodes, edges and floor plans."""
    templates = {
        'nodes': ('navigation_nodes_template.csv', NODE_CSV_TEMPLATE),
        'edges': ('navigation_edges_template.csv', EDGE_CSV_TEMPLATE),
        'floorplans': ('floor_plans_template.csv', FLOORPLAN_CSV_TEMPLATE),
    }
    if kind not in templates:
        flash("Unknown template type.", "danger")
        return redirect(url_for('admin.manage_navigation'))
    filename, content = templates[kind]
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

def _csv_row_to_bool(value, default=False):
    return str(value).strip().lower() in ('true', '1', 'yes', 'y') if value not in (None, '') else default

@admin_bp.route('/navigation/import', methods=['POST'])
@admin_bp.route('/navigation/import/<kind>', methods=['POST'])
@role_required('main_admin')
def import_navigation_data(kind=None):
    """Bulk-imports campus data (nodes / edges / floor plans) from an uploaded CSV file."""
    user = get_current_user()
    kind = kind or request.form.get('kind', 'nodes')
    file = request.files.get('csv_file')
    if not file or not file.filename.lower().endswith('.csv'):
        flash("A .csv file is required for data import.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    try:
        rows = list(csv.DictReader(io.StringIO(file.read().decode('utf-8-sig'))))
    except Exception as exc:
        flash(f"Could not read CSV file: {exc}", "danger")
        return redirect(url_for('admin.manage_navigation'))

    created, skipped = 0, 0

    if kind == 'nodes':
        for row in rows:
            code = (row.get('node_code') or '').strip().upper()
            if not code or not (row.get('name') or '').strip() or not (row.get('building') or '').strip():
                skipped += 1
                continue
            if NavigationNode.query.filter_by(node_code=code).first():
                skipped += 1
                continue
            try:
                db.session.add(NavigationNode(
                    node_code=code, name=row['name'].strip(), building=row['building'].strip(),
                    floor=(row.get('floor') or 'Ground Floor').strip(),
                    category=(row.get('category') or 'Classroom').strip(),
                    description=(row.get('description') or '').strip(),
                    x_coord=int(row.get('x_coord') or 0), y_coord=int(row.get('y_coord') or 0),
                    photo_url=(row.get('photo_url') or '').strip() or None,
                    is_panoramic=_csv_row_to_bool(row.get('is_panoramic')),
                    is_accessible=_csv_row_to_bool(row.get('is_accessible'), True),
                    is_sample_data=_csv_row_to_bool(row.get('is_sample_data'), True)
                ))
                created += 1
            except Exception:
                skipped += 1
    elif kind == 'edges':
        node_map = {n.node_code: n.id for n in NavigationNode.query.all()}
        for row in rows:
            src = node_map.get((row.get('source_node_code') or '').strip().upper())
            dst = node_map.get((row.get('target_node_code') or '').strip().upper())
            if not src or not dst or src == dst or NavigationEdge.query.filter_by(source_node_id=src, target_node_id=dst).first():
                skipped += 1
                continue
            try:
                db.session.add(NavigationEdge(
                    source_node_id=src, target_node_id=dst,
                    distance_meters=float(row.get('distance_meters') or 15.0),
                    direction_hint=(row.get('direction_hint') or '').strip() or None,
                    is_bidirectional=_csv_row_to_bool(row.get('is_bidirectional'), True),
                    is_sample_data=_csv_row_to_bool(row.get('is_sample_data'), True)
                ))
                created += 1
            except Exception:
                skipped += 1
    elif kind == 'floorplans':
        for row in rows:
            building = (row.get('building') or '').strip()
            title = (row.get('title') or '').strip()
            if not building or not title:
                skipped += 1
                continue
            db.session.add(CampusFloorPlan(
                building=building, floor=(row.get('floor') or 'Ground Floor').strip(),
                title=title, image_url=(row.get('image_url') or '').strip() or None,
                is_sample_data=_csv_row_to_bool(row.get('is_sample_data'), True)
            ))
            created += 1
    else:
        flash("Unknown import type.", "danger")
        return redirect(url_for('admin.manage_navigation'))

    db.session.commit()
    AuditLog.log(action='NAV_DATA_IMPORTED', module='NAVIGATION', user_id=user.id,
                 details=f"Imported {kind} CSV: {created} created, {skipped} skipped.", ip_address=request.remote_addr)
    flash(f"Import finished: {created} {kind} record(s) created, {skipped} skipped.", "success")
    return redirect(url_for('admin.manage_navigation'))
