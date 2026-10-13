import os
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify, abort
from app.blueprints.lost_found import lost_found_bp
from app.models import LostFoundItem, LostFoundMatch, LostFoundClaim, Notification, AuditLog, User
from app.database import db
from app.utils.auth_helpers import login_required, restrict_visitors, get_current_user
from app.utils.image_matcher import (
    extract_image_features, rank_matches, validate_image_bytes, find_duplicate_report,
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 MB upload ceiling

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _admin_ids():
    return [u.id for u in User.query.filter_by(role='main_admin', is_active=True).all()]

@lost_found_bp.route('/')
def index():
    """Module 2: AI Lost & Found items catalog."""
    user = get_current_user()
    report_type = request.args.get('type')
    category = request.args.get('category')
    status_f = request.args.get('status')
    search = request.args.get('q', '').strip()

    query = LostFoundItem.query.order_by(LostFoundItem.date_time_reported.desc())

    if report_type in ['lost', 'found']:
        query = query.filter_by(report_type=report_type)

    if category:
        query = query.filter_by(category=category)

    if status_f in ('open', 'matched', 'claimed', 'closed'):
        query = query.filter_by(status=status_f)

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
        current_status=status_f,
        search_query=search
    )

@lost_found_bp.route('/report', methods=['GET', 'POST'])
@login_required
@restrict_visitors
def report_item():
    """Report a lost or found item with photograph, AI embedding and contextual ranking."""
    user = get_current_user()

    if request.method == 'POST':
        report_type = request.form.get('report_type')
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        location_reported = request.form.get('location_reported', '').strip()
        description = request.form.get('description', '').strip()
        color_hint = request.form.get('color_hint', '').strip() or None
        contact_phone = request.form.get('contact_phone', user.phone or '').strip()

        if not title or not location_reported or not description or report_type not in ['lost', 'found']:
            flash("Please fill in all required fields.", "warning")
            return redirect(url_for('lost_found.report_item'))

        # Handle file upload with Phase 4 content validation
        photo_rel_url = None
        feature_vector_json = None
        file = request.files.get('photo')

        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Photograph rejected: only PNG, JPG, JPEG or WEBP images are allowed.", "danger")
                return redirect(url_for('lost_found.report_item'))
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            if size > MAX_PHOTO_BYTES:
                flash("Photograph rejected: file exceeds the 8 MB limit.", "danger")
                return redirect(url_for('lost_found.report_item'))
            if not validate_image_bytes(file):
                flash("Photograph rejected: file content is not a valid image.", "danger")
                return redirect(url_for('lost_found.report_item'))

            filename = secure_filename(f"lf_{int(datetime.utcnow().timestamp())}_{file.filename}")
            upload_dir = Path(current_app.root_path) / "static" / "uploads" / "lost_found"
            upload_dir.mkdir(parents=True, exist_ok=True)
            saved_path = upload_dir / filename
            file.save(saved_path)
            photo_rel_url = f"/static/uploads/lost_found/{filename}"

            # Generate image embedding (pretrained CNN when available, HSV fallback)
            feature_vector_json = extract_image_features(str(saved_path))

        new_item = LostFoundItem(
            user_id=user.id,
            report_type=report_type,
            title=title,
            category=category,
            location_reported=location_reported,
            date_time_reported=datetime.utcnow(),
            description=description,
            color_hint=color_hint,
            photo_url=photo_rel_url,
            image_feature_vector=feature_vector_json,
            contact_phone=contact_phone,
            status='open'
        )
        db.session.add(new_item)
        db.session.flush() # obtain new_item.id

        # PHASE 5: duplicate-report detection (same user re-reporting one item).
        # Duplicates are kept for audit but skip AI matching so no duplicate
        # match rows or duplicate notifications can be generated for them.
        dup_min = current_app.config.get('LF_DUPLICATE_SCORE', 0.65)
        dup_candidates = LostFoundItem.query.filter_by(
            user_id=user.id, report_type=report_type).all()
        duplicate = find_duplicate_report(new_item, dup_candidates, min_score=dup_min)
        if duplicate:
            new_item.is_duplicate = True
            new_item.duplicate_of_id = duplicate["item_id"]
            AuditLog.log(action='LF_DUPLICATE_REPORT_FLAGGED', module='LOST_FOUND', user_id=user.id,
                         details=f"Report '{title}' flagged as duplicate of item #{duplicate['item_id']} "
                                 f"(score {duplicate['score']}).", ip_address=request.remote_addr)
            db.session.commit()
            flash(f"Item reported. This looks like a duplicate of your earlier report "
                  f"'{duplicate['title']}', so it was linked to that report and no duplicate "
                  f"match alerts were sent.", "info")
            return redirect(url_for('lost_found.item_detail', item_id=new_item.id))

        # PHASE 4/5: contextual + image composite ranking against counterpart reports
        min_composite = current_app.config.get('LF_MATCH_MIN_COMPOSITE', 0.35)
        strong = current_app.config.get('LF_STRONG_MATCH_SCORE', 0.70)
        medium = current_app.config.get('LF_MEDIUM_MATCH_SCORE', 0.50)
        match_limit = current_app.config.get('LF_MATCH_LIMIT', 10)
        match_count = 0
        ranked = []
        if feature_vector_json or description:
            opposite_type = 'found' if report_type == 'lost' else 'lost'
            candidates = LostFoundItem.query.filter_by(report_type=opposite_type, status='open').all()
            candidates = [c for c in candidates if c.id != new_item.id]
            ranked = rank_matches(new_item, candidates, min_composite=min_composite,
                                  limit=match_limit, strong=strong, medium=medium)
            import json as _json
            # PHASE 5: one match row per item pair - a re-occurring pair updates
            # nothing and re-notifies no one (duplicate suggestion prevention)
            existing_pairs = {
                (m.lost_item_id, m.found_item_id)
                for m in LostFoundMatch.query.filter(
                    db.or_(LostFoundMatch.lost_item_id == new_item.id,
                          LostFoundMatch.found_item_id == new_item.id)).all()
            }
            for m in ranked:
                lost_id = new_item.id if report_type == 'lost' else m["item_id"]
                found_id = m["item_id"] if report_type == 'lost' else new_item.id
                if (lost_id, found_id) in existing_pairs:
                    continue
                match_entry = LostFoundMatch(
                    lost_item_id=lost_id,
                    found_item_id=found_id,
                    similarity_score=m["image_score"],
                    composite_score=m["composite_score"],
                    factors=_json.dumps(m["factors"]),
                    status='suggested'
                )
                db.session.add(match_entry)
                match_count += 1

        # PHASE 4/5: targeted in-app notifications (only the involved users are
        # alerted, and the dedup_key makes the same match alert idempotent)
        counterpart_title = "Found item" if report_type == 'lost' else "Lost item"
        for m in ranked:
            counterpart = db.session.get(LostFoundItem, m["item_id"])
            if not counterpart:
                continue
            lost_id = new_item.id if report_type == 'lost' else m["item_id"]
            found_id = m["item_id"] if report_type == 'lost' else new_item.id
            pair_key = f"pair:{lost_id}-{found_id}"
            if report_type == 'lost':
                Notification.notify(
                    user.id,
                    title="Possible match found for your lost item",
                    message=(f"Possible match found for your lost item '{title}'. "
                             f"Location: {counterpart.location_reported}. "
                             f"Similarity confidence {round(m['composite_score'] * 100)}%. "
                             "Please check the report and follow the collection instructions."),
                    category='match',
                    link_url=url_for('lost_found.item_detail', item_id=new_item.id),
                    dedup_key=f"lf-match:{pair_key}:u{user.id}")
                Notification.notify(
                    counterpart.user_id,
                    title="A new lost report resembles your found item",
                    message=(f"A newly reported lost item '{title}' closely matches the '{counterpart.title}' "
                             f"you submitted (confidence {round(m['composite_score'] * 100)}%). "
                             "Please review the match. Similarity alone is not proof of ownership."),
                    category='match',
                    link_url=url_for('lost_found.item_detail', item_id=counterpart.id),
                    dedup_key=f"lf-match:{pair_key}:u{counterpart.user_id}")
            else:
                Notification.notify(
                    user.id,
                    title="A lost report matches the item you found",
                    message=(f"Your found item '{title}' resembles an existing lost report of "
                             f"'{counterpart.title}' (confidence {round(m['composite_score'] * 100)}%). "
                             "Please review before handing the item over."),
                    category='match',
                    link_url=url_for('lost_found.item_detail', item_id=new_item.id),
                    dedup_key=f"lf-match:{pair_key}:u{user.id}")
                Notification.notify(
                    counterpart.user_id,
                    title="Possible match found for your lost item",
                    message=(f"Possible match found for your lost item '{counterpart.title}'. "
                             f"Location: {new_item.location_reported}. "
                             f"Similarity confidence {round(m['composite_score'] * 100)}%. "
                             "Please check the report and follow the collection instructions."),
                    category='match',
                    link_url=url_for('lost_found.item_detail', item_id=counterpart.id),
                    dedup_key=f"lf-match:{pair_key}:u{counterpart.user_id}")

        AuditLog.log(action='LF_REPORT_SUBMITTED', module='LOST_FOUND', user_id=user.id,
                     details=f"{report_type.upper()} report '{title}' at {location_reported}; {match_count} possible match(es).",
                     ip_address=request.remote_addr)
        db.session.commit()

        if match_count > 0:
            flash(f"Item reported successfully! The AI matcher identified {match_count} potential match(es), and involved users were notified.", "success")
        else:
            flash("Item reported successfully. We will monitor new entries for similarity matches.", "success")

        return redirect(url_for('lost_found.item_detail', item_id=new_item.id))

    categories = ['Electronics', 'ID Cards & Docs', 'Books & Stationery', 'Personal Items', 'Valuables', 'Other']
    return render_template('lost_found/report.html', user=user, categories=categories)

@lost_found_bp.route('/item/<int:item_id>')
def item_detail(item_id):
    """View item details and AI similarity suggestions (authorized parties only)."""
    user = get_current_user()
    item = LostFoundItem.query.get_or_404(item_id)

    is_owner = bool(user and user.id == item.user_id)
    is_admin = bool(user and user.role == 'main_admin')

    # PHASE 4 SECURITY: private report data (contact & reporter identity)
    # is visible only to the reporter and Main Admin. Others coordinate via claims.
    mask_contact = not (is_owner or is_admin)

    # Possible matches are shown only to the report owner and Main Admin
    matches = []
    if is_owner or is_admin:
        rank_expr = db.func.coalesce(LostFoundMatch.composite_score, LostFoundMatch.similarity_score)
        if item.report_type == 'lost':
            matches = LostFoundMatch.query.filter_by(lost_item_id=item.id).order_by(rank_expr.desc()).all()
        else:
            matches = LostFoundMatch.query.filter_by(found_item_id=item.id).order_by(rank_expr.desc()).all()

    # The owner sees that claims exist; claim proof statements are admin-only
    claims = []
    if is_owner or is_admin:
        claims = LostFoundClaim.query.filter_by(item_id=item.id).order_by(LostFoundClaim.created_at.desc()).all()

    my_pending_claim = None
    if user:
        my_pending_claim = LostFoundClaim.query.filter_by(item_id=item.id, claimant_id=user.id, status='pending').first()

    return render_template(
        'lost_found/detail.html',
        user=user, item=item, matches=matches, claims=claims,
        mask_contact=mask_contact, is_owner=is_owner, is_admin=is_admin,
        my_pending_claim=my_pending_claim)

@lost_found_bp.route('/item/<int:item_id>/claim', methods=['POST'])
@login_required
@restrict_visitors
def claim_item(item_id):
    """PHASE 4: formal ownership claim - requires a proof statement and admin verification."""
    user = get_current_user()
    item = LostFoundItem.query.get_or_404(item_id)

    proof_statement = request.form.get('proof_statement', '').strip()
    if len(proof_statement) < 15:
        flash("Please describe why this item belongs to you (at least 15 characters). Your statement stays private and is reviewed only by campus administration.", "warning")
        return redirect(url_for('lost_found.item_detail', item_id=item.id))

    if item.user_id == user.id:
        flash("You cannot claim your own report.", "danger")
        return redirect(url_for('lost_found.item_detail', item_id=item.id))

    if item.status == 'closed':
        flash("This item has already been returned to its owner.", "info")
        return redirect(url_for('lost_found.item_detail', item_id=item.id))

    existing = LostFoundClaim.query.filter_by(item_id=item.id, claimant_id=user.id, status='pending').first()
    if existing:
        flash("You already have a pending claim on this item awaiting verification.", "info")
        return redirect(url_for('lost_found.item_detail', item_id=item.id))

    claim = LostFoundClaim(item_id=item.id, claimant_id=user.id, proof_statement=proof_statement, status='pending')
    db.session.add(claim)
    item.status = 'claimed'
    item.claimed_by_user_id = user.id

    # Notify only the involved parties: the finder/reporter and campus administration
    Notification.notify(
        item.user_id,
        title=f"Someone claimed the '{item.title}' you reported",
        message=(f"A claim was submitted for the item you reported as '{item.title}'. "
                 "Campus administration will verify ownership before handover. "
                 "Please keep the physical item secure until contacted."),
        category='claim',
        link_url=url_for('lost_found.item_detail', item_id=item.id))
    for admin_id in _admin_ids():
        Notification.notify(
            admin_id,
            title="New ownership claim awaiting verification",
            message=(f"User '{user.full_name}' claimed the report '{item.title}' "
                     f"({item.report_type.upper()}). Review the private proof statement and verify."),
            category='claim',
            link_url=url_for('admin.manage_lost_found'))

    AuditLog.log(action='LF_CLAIM_SUBMITTED', module='LOST_FOUND', user_id=user.id,
                 details=f"Claim #{claim.id if claim.id else 'new'} on item '{item.title}' (id {item.id}).",
                 ip_address=request.remote_addr)
    db.session.commit()

    flash("Claim submitted. Campus administration has been notified and will verify ownership before any handover.", "success")
    return redirect(url_for('lost_found.item_detail', item_id=item.id))

@lost_found_bp.route('/my-reports')
@login_required
def my_reports():
    """Phase 4: personal dashboard of the user's reports, matches and claim outcomes."""
    user = get_current_user()
    items = LostFoundItem.query.filter_by(user_id=user.id).order_by(LostFoundItem.date_time_reported.desc()).all()
    claims = LostFoundClaim.query.filter_by(claimant_id=user.id).order_by(LostFoundClaim.created_at.desc()).all()
    return render_template('lost_found/my_reports.html', user=user, items=items, claims=claims)
