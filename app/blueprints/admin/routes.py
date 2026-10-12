from flask import render_template, request, redirect, url_for, flash
from app.blueprints.admin import admin_bp
from app.models import User, NavigationNode, NavigationEdge, LostFoundItem, CanteenItem, CanteenOrder, AuditLog
from app.database import db
from app.utils.auth_helpers import role_required, get_current_user

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
