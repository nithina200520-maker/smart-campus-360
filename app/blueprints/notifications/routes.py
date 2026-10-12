from flask import render_template, request, redirect, url_for, flash
from app.blueprints.notifications import notifications_bp
from app.models import Notification
from app.database import db
from app.utils.auth_helpers import login_required, get_current_user

@notifications_bp.route('/')
@login_required
def index():
    """PHASE 4: personal notification history (in-app only; no email dependency)."""
    user = get_current_user()
    only_unread = request.args.get('unread') == '1'
    query = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc())
    if only_unread:
        query = query.filter_by(is_read=False)
    notifications = query.limit(200).all()
    return render_template('notifications/list.html', user=user,
                           notifications=notifications, only_unread=only_unread)

@notifications_bp.route('/mark-read/<int:note_id>', methods=['POST'])
@login_required
def mark_read(note_id):
    note = Notification.query.get_or_404(note_id)
    if note.user_id != get_current_user().id:
        abort_forbidden()
    note.is_read = True
    db.session.commit()
    return redirect(url_for('notifications.index'))

@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for('notifications.index'))

def abort_forbidden():
    from flask import abort
    abort(403)
