import re
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, current_app, abort
from app.blueprints.auth import auth_bp
from app.models import User, AuditLog
from app.database import db
from app.utils.auth_helpers import login_user, logout_user, login_required, get_current_user

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Enforces minimum 8 characters, with letters and numbers."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one alphabetical letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one numeric digit."
    return True, ""

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Secure user authentication with credential validation and audit logging."""
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_active:
                AuditLog.log(
                    action='LOGIN_BLOCKED_INACTIVE',
                    module='AUTH',
                    user_id=user.id,
                    details=f"Deactivated account '{email}' attempted sign in.",
                    ip_address=request.remote_addr
                )
                flash("Your account has been deactivated by administration. Please contact the Main Admin.", "danger")
                return render_template('auth/login.html')

            login_user(user)

            AuditLog.log(
                action='USER_LOGIN_SUCCESS',
                module='AUTH',
                user_id=user.id,
                details=f"User signed in as {user.role.upper()} (Verified={user.is_verified})",
                ip_address=request.remote_addr
            )

            # Flash role-specific welcome message
            if user.role == 'teacher':
                if user.is_verified:
                    flash(f"Welcome Dr./Prof. {user.full_name}! Faculty status verified - Teacher-First Priority is ACTIVE.", "success")
                else:
                    flash(f"Welcome {user.full_name}! Your teacher account is awaiting Main Admin verification for canteen priority.", "warning")
            else:
                flash(f"Welcome back, {user.full_name}! Signed in as [{user.role.replace('_', ' ').title()}].", "success")

            next_page = request.args.get('next')
            if next_page and not next_page.startswith('//') and not next_page.startswith('http'):
                return redirect(next_page)

            # Role-based landing redirects
            if user.role == 'main_admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'canteen_admin':
                return redirect(url_for('canteen_admin.dashboard'))
            else:
                return redirect(url_for('main.index'))
        else:
            AuditLog.log(
                action='USER_LOGIN_FAILED',
                module='AUTH',
                details=f"Failed login attempt for email '{email}'",
                ip_address=request.remote_addr
            )
            flash("Invalid email address or password. Please verify your credentials.", "danger")

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Role-specific registration for Students, Teachers, and Visitors.
    Security: Never allows public registration to create Main Admin or Canteen Admin accounts.
    Teacher verification: Teacher accounts default to is_verified=False pending Main Admin approval.
    """
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'student').strip().lower()
        department = request.form.get('department', '').strip()
        phone = request.form.get('phone', '').strip()

        # Strict security enforcement: Disallow public creation of admin accounts
        if role in ['main_admin', 'canteen_admin']:
            AuditLog.log(
                action='UNAUTHORIZED_ADMIN_REGISTRATION_ATTEMPT',
                module='AUTH',
                details=f"Blocked attempt to register public account with administrative role '{role}' for '{email}'.",
                ip_address=request.remote_addr
            )
            flash("Security Violation: Administrative roles cannot be registered through public registration.", "danger")
            return redirect(url_for('auth.register'))

        if role not in ['student', 'teacher', 'visitor']:
            role = 'student'

        if not full_name or not email or not password:
            flash("Please fill in all required fields.", "warning")
            return render_template('auth/register.html')

        if password != confirm_password:
            flash("Passwords do not match.", "warning")
            return render_template('auth/register.html')

        is_valid, msg = validate_password_strength(password)
        if not is_valid:
            flash(msg, "warning")
            return render_template('auth/register.html')

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("An account with this email address is already registered.", "danger")
            return render_template('auth/register.html')

        # Role-specific fields
        designation = None
        semester = None
        purpose_of_visit = None
        usn_or_emp_id = None
        is_verified = True # Students and visitors are active directly

        if role == 'teacher':
            usn_or_emp_id = request.form.get('employee_id', '').strip()
            designation = request.form.get('designation', 'Assistant Professor').strip()
            # Crucial requirement: Teacher priority is granted ONLY to verified teacher accounts!
            is_verified = False
        elif role == 'student':
            usn_or_emp_id = request.form.get('usn', '').strip().upper()
            semester = request.form.get('semester', '1st Semester').strip()
        elif role == 'visitor':
            purpose_of_visit = request.form.get('purpose_of_visit', 'Campus Visit').strip()

        new_user = User(
            full_name=full_name,
            email=email,
            role=role,
            department=department,
            phone=phone,
            usn_or_emp_id=usn_or_emp_id,
            designation=designation,
            semester=semester,
            purpose_of_visit=purpose_of_visit,
            is_verified=is_verified,
            is_active=True
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        if role == 'teacher':
            AuditLog.log(
                action='TEACHER_REGISTERED_PENDING_VERIFICATION',
                module='AUTH',
                user_id=new_user.id,
                details=f"Faculty '{full_name}' ({designation}, {department}, Emp ID: {usn_or_emp_id}) registered. Verification pending.",
                ip_address=request.remote_addr
            )
            flash("Faculty registration successful! Your Employee ID has been submitted for Main Admin verification. Once verified, Teacher-First Priority will activate automatically.", "info")
        else:
            AuditLog.log(
                action='USER_REGISTERED',
                module='AUTH',
                user_id=new_user.id,
                details=f"New {role.upper()} account registered: {full_name} ({email})",
                ip_address=request.remote_addr
            )
            flash("Registration successful! You may now sign in.", "success")

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request: generates secure, time-sensitive reset token."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user and user.is_active:
            token = user.generate_reset_token()
            db.session.commit()

            AuditLog.log(
                action='PASSWORD_RESET_TOKEN_GENERATED',
                module='AUTH',
                user_id=user.id,
                details=f"Password reset token requested for '{email}'",
                ip_address=request.remote_addr
            )

            reset_url = url_for('auth.reset_password', token=token, _external=True)
            # In development/local demonstration, display link directly
            flash(f"Password reset link generated (valid for 30 minutes). Click below to proceed:", "info")
            return render_template('auth/forgot_password.html', reset_url=reset_url, reset_token=token)
        else:
            # Generic response to prevent user enumeration
            flash("If that email address exists in our database, password reset instructions have been generated.", "info")
            return render_template('auth/forgot_password.html')

    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Verifies reset token and updates account password."""
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.verify_reset_token(token):
        flash("Password reset link is invalid or has expired (valid for 30 minutes). Please request a new link.", "danger")
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            flash("Passwords do not match.", "warning")
            return render_template('auth/reset_password.html', token=token, user=user)

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            flash(msg, "warning")
            return render_template('auth/reset_password.html', token=token, user=user)

        user.set_password(new_password)
        user.clear_reset_token()
        db.session.commit()

        AuditLog.log(
            action='PASSWORD_RESET_COMPLETED',
            module='AUTH',
            user_id=user.id,
            details=f"Password reset completed successfully for '{user.email}'",
            ip_address=request.remote_addr
        )

        flash("Your password has been updated successfully! Please sign in with your new credentials.", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token, user=user)

@auth_bp.route('/logout')
def logout():
    """Securely clears session and records sign out audit."""
    current_user = get_current_user()
    if current_user:
        AuditLog.log(
            action='USER_LOGOUT',
            module='AUTH',
            user_id=current_user.id,
            details=f"User signed out ({current_user.role})",
            ip_address=request.remote_addr
        )

    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for('main.index'))

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile overview showcasing role details and verification status."""
    user = get_current_user()
    return render_template('auth/profile.html', user=user)

@auth_bp.route('/quick-switch/<role>')
def quick_switch(role):
    """
    Developer convenience helper to test application roles in 1 click.
    Switches active session to a seed user of the requested role.

    SECURITY (Phase 2): This endpoint is a privilege-escalation surface
    (no credentials required). It is therefore restricted to the development
    environment only via Config.ALLOW_QUICK_SWITCH; any attempt in production
    is refused, audited, and returns HTTP 403.
    """
    if not current_app.config.get('ALLOW_QUICK_SWITCH', False):
        AuditLog.log(
            action='QUICK_SWITCH_BLOCKED_PRODUCTION',
            module='AUTH',
            details=f"Security: blocked /auth/quick-switch/{role} attempt outside development environment.",
            ip_address=request.remote_addr
        )
        abort(403)

    user = User.query.filter_by(role=role).first()
    if user:
        login_user(user)
        flash(f"Switched role to {user.role.upper()} ({user.full_name}) for testing.", "info")
        if role == 'main_admin':
            return redirect(url_for('admin.dashboard'))
        elif role == 'canteen_admin':
            return redirect(url_for('canteen_admin.dashboard'))
        return redirect(url_for('main.index'))
    else:
        flash(f"Seed user with role '{role}' not found. Please run init_db.py.", "warning")
        return redirect(url_for('main.index'))
