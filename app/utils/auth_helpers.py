from functools import wraps
from flask import session, redirect, url_for, flash, request
from app.models import User, AuditLog

def get_current_user():
    """
    Retrieves the current authenticated user from session.
    If the account has been deactivated in the database, automatically
    invalidates the active session for real-time security.
    """
    user_id = session.get('user_id')
    if not user_id:
        return None

    user = User.query.get(user_id)
    if not user:
        logout_user()
        return None

    if not user.is_active:
        logout_user()
        flash("Your account has been deactivated by administration. Please contact the Main Admin.", "danger")
        return None

    return user

def login_user(user):
    """
    Establishes an authenticated session for the given user,
    preventing session fixation by re-initializing session keys.
    """
    session.clear()
    session.permanent = True
    session['user_id'] = user.id
    session['user_name'] = user.full_name
    session['user_email'] = user.email
    session['user_role'] = user.role
    session['is_verified'] = bool(user.is_verified)

def logout_user():
    """Completely purges the active session."""
    session.clear()

def login_required(f):
    """Decorator ensuring the user is signed in with an active account."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    """
    Decorator restricting route access to specified roles.
    Main Admin possesses universal clearance across all endpoints.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for('auth.login', next=request.path))

            # Main Admin has master access to all routes
            if user.role == 'main_admin':
                return f(*args, **kwargs)

            if user.role not in allowed_roles:
                # Phase 2 SECURITY: audit every failed authorization attempt
                AuditLog.log(
                    action='ACCESS_DENIED_ROLE',
                    module='ADMIN',
                    user_id=user.id,
                    details=f"User '{user.email}' (role={user.role}) was denied access to '{request.path}' requiring [{', '.join(allowed_roles)}].",
                    ip_address=request.remote_addr
                )
                flash(f"Access denied: This section requires privileges for [{', '.join(allowed_roles)}].", "danger")
                return redirect(url_for('main.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def verified_teacher_required(f):
    """Decorator ensuring only verified faculty can access specific teacher privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Please sign in as a teacher.", "warning")
            return redirect(url_for('auth.login', next=request.path))

        if user.role == 'main_admin':
            return f(*args, **kwargs)

        if user.role != 'teacher':
            flash("This feature is reserved for teaching faculty.", "danger")
            return redirect(url_for('main.index'))

        if not user.is_verified:
            flash("Teacher verification pending: Your Employee ID is awaiting Main Admin verification before faculty priority is granted.", "warning")
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)
    return decorated_function

def restrict_visitors(f):
    """
    Decorator preventing visitor accounts from accessing private user data
    (student grades, attendance, faculty records, or private order logs).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user and user.role == 'visitor':
            flash("Notice: Visitors are restricted from accessing private campus user directories.", "warning")
            return redirect(url_for('navigation.index'))
        return f(*args, **kwargs)
    return decorated_function
