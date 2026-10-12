import os
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from app.blueprints.lost_found import lost_found_bp
from app.models import LostFoundItem, LostFoundMatch, AuditLog
from app.database import db
from app.utils.auth_helpers import login_required, restrict_visitors, get_current_user
from app.utils.image_matcher import extract_image_features, match_item_against_catalog

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@lost_found_bp.route('/')
def index():
    """Module 2: AI Lost & Found items catalog."""
    user = get_current_user()
    report_type = request.args.get('type')
    category = request.args.get('category')
    search = request.args.get('q', '').strip()

    query = LostFoundItem.query.order_by(LostFoundItem.date_time_reported.desc())

    if report_type in ['lost', 'found']:
        query = query.filter_by(report_type=report_type)

    if category:
        query = query.filter_by(category=category)

    if search:
        query = query.filter(
            (LostFoundItem.title.ilike(f"%{search}%")) |
            (LostFoundItem.description.ilike(f"%{search}%")) |
            (LostFoundItem.location_reported.ilike(f"%{search}%"))
        )

    items = query.all()
    categories = ['Electronics', 'ID Cards & Docs', 'Books & Stationery', 'Personal Items', 'Valuables', 'Other']

    return render_template(
        'lost_found/index.html',
        user=user,
        items=items,
        categories=categories,
        current_type=report_type,
        current_cat=category,
        search_query=search
    )

@lost_found_bp.route('/report', methods=['GET', 'POST'])
@login_required
def report_item():
    """Report a lost or found item with photograph and AI similarity extraction."""
    user = get_current_user()

    if request.method == 'POST':
        report_type = request.form.get('report_type')
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        location_reported = request.form.get('location_reported', '').strip()
        description = request.form.get('description', '').strip()
        contact_phone = request.form.get('contact_phone', user.phone or '').strip()

        if not title or not location_reported or not description or report_type not in ['lost', 'found']:
            flash("Please fill in all required fields.", "warning")
            return redirect(url_for('lost_found.report_item'))

        # Handle file upload
        photo_rel_url = None
        feature_vector_json = None
        file = request.files.get('photo')

        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"lf_{int(datetime.utcnow().timestamp())}_{file.filename}")
            upload_dir = Path(current_app.root_path) / "static" / "uploads" / "lost_found"
            upload_dir.mkdir(parents=True, exist_ok=True)
            saved_path = upload_dir / filename
            file.save(saved_path)
            photo_rel_url = f"/static/uploads/lost_found/{filename}"

            # Extract image embedding features with OpenCV
            feature_vector_json = extract_image_features(str(saved_path))

        new_item = LostFoundItem(
            user_id=user.id,
            report_type=report_type,
            title=title,
            category=category,
            location_reported=location_reported,
            date_time_reported=datetime.utcnow(),
            description=description,
            photo_url=photo_rel_url,
            image_feature_vector=feature_vector_json,
            contact_phone=contact_phone,
            status='open'
        )
        db.session.add(new_item)
        db.session.flush() # obtain new_item.id

        # Trigger AI similarity matching against candidate counterparts
        match_count = 0
        if feature_vector_json:
            opposite_type = 'found' if report_type == 'lost' else 'lost'
            candidate_items = LostFoundItem.query.filter_by(report_type=opposite_type, status='open').all()
            
            similar_matches = match_item_against_catalog(feature_vector_json, candidate_items, min_similarity=0.55)
            for m in similar_matches:
                match_entry = LostFoundMatch(
                    lost_item_id=new_item.id if report_type == 'lost' else m["item_id"],
                    found_item_id=m["item_id"] if report_type == 'lost' else new_item.id,
                    similarity_score=m["confidence_decimal"],
                    status='suggested'
                )
                db.session.add(match_entry)
                match_count += 1

        db.session.commit()

        if match_count > 0:
            flash(f"Item reported successfully! AI Matcher identified {match_count} potential match(es) in the campus registry.", "success")
        else:
            flash("Item reported successfully. We will monitor new entries for similarity matches.", "success")

        return redirect(url_for('lost_found.item_detail', item_id=new_item.id))

    categories = ['Electronics', 'ID Cards & Docs', 'Books & Stationery', 'Personal Items', 'Valuables', 'Other']
    return render_template('lost_found/report.html', user=user, categories=categories)

@lost_found_bp.route('/item/<int:item_id>')
def item_detail(item_id):
    """View item details and AI similarity suggestions."""
    user = get_current_user()
    item = LostFoundItem.query.get_or_404(item_id)

    # Phase 2 SECURITY: Visitor accounts must not access private user data
    # (reporter identity & contact number) unless they own the report.
    # Main Admin / Canteen Admin retain oversight access; other roles unchanged.
    mask_contact = bool(
        user and user.role == 'visitor'
        and item.user_id != user.id
        and user.role != 'main_admin'
    )

    # Fetch any AI suggested matches
    if item.report_type == 'lost':
        matches = LostFoundMatch.query.filter_by(lost_item_id=item.id).order_by(LostFoundMatch.similarity_score.desc()).all()
    else:
        matches = LostFoundMatch.query.filter_by(found_item_id=item.id).order_by(LostFoundMatch.similarity_score.desc()).all()

    return render_template('lost_found/detail.html', user=user, item=item, matches=matches, mask_contact=mask_contact)

@lost_found_bp.route('/item/<int:item_id>/claim', methods=['POST'])
@login_required
@restrict_visitors
def claim_item(item_id):
    """Submit a collection / ownership claim request."""
    user = get_current_user()
    item = LostFoundItem.query.get_or_404(item_id)

    item.claimed_by_user_id = user.id
    item.status = 'matched'
    db.session.commit()

    flash(f"Claim request recorded for '{item.title}'. Campus administration has been notified for identity verification.", "info")
    return redirect(url_for('lost_found.item_detail', item_id=item.id))
