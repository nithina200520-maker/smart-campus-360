import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db

class User(db.Model):
    """User account model supporting all 5 application roles."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Roles: main_admin, canteen_admin, teacher, student, visitor
    role = db.Column(db.String(30), nullable=False, default='student', index=True)
    department = db.Column(db.String(100), nullable=True) # e.g. CSE, ECE, ME, Civil, Admin
    phone = db.Column(db.String(20), nullable=True)
    usn_or_emp_id = db.Column(db.String(50), nullable=True)
    designation = db.Column(db.String(100), nullable=True) # e.g. Professor, Assistant Professor, HOD
    semester = db.Column(db.String(20), nullable=True) # e.g. 1st Sem, 3rd Sem, 5th Sem, 7th Sem
    purpose_of_visit = db.Column(db.String(150), nullable=True) # For visitors: e.g. Parent Meeting, Campus Tour
    is_verified = db.Column(db.Boolean, default=True, nullable=False) # For teachers: requires Main Admin verification for canteen priority
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    reset_token = db.Column(db.String(100), nullable=True, index=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    lost_found_reports = db.relationship('LostFoundItem', backref='reporter', lazy=True, foreign_keys='LostFoundItem.user_id')
    canteen_orders = db.relationship('CanteenOrder', backref='customer', lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_main_admin(self) -> bool:
        return self.role == 'main_admin'

    def is_canteen_admin(self) -> bool:
        return self.role in ('main_admin', 'canteen_admin')

    def is_teacher(self) -> bool:
        return self.role == 'teacher'

    def is_verified_teacher(self) -> bool:
        """Returns True only if user is a teacher AND verified by Main Admin."""
        return self.role == 'teacher' and bool(self.is_verified)

    def generate_reset_token(self) -> str:
        """Generates a secure 48-character token valid for 30 minutes."""
        self.reset_token = secrets.token_urlsafe(36)
        self.reset_token_expiry = datetime.utcnow() + timedelta(minutes=30)
        return self.reset_token

    def verify_reset_token(self, token: str) -> bool:
        """Validates token authenticity and expiration (constant-time comparison)."""
        if not self.reset_token or not self.reset_token_expiry:
            return False
        if not secrets.compare_digest(self.reset_token, token):
            return False
        return datetime.utcnow() <= self.reset_token_expiry

    def clear_reset_token(self):
        """Clears the token after successful password reset."""
        self.reset_token = None
        self.reset_token_expiry = None

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "department": self.department,
            "phone": self.phone,
            "usn_or_emp_id": self.usn_or_emp_id,
            "designation": self.designation,
            "semester": self.semester,
            "purpose_of_visit": self.purpose_of_visit,
            "is_verified": self.is_verified,
            "is_active": self.is_active,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None
        }

    def __repr__(self):
        return f"<User {self.email} ({self.role}, verified={self.is_verified})>"


class NavigationNode(db.Model):
    """
    Campus location node for map search, routing, and Street View/photo POIs.
    Contains clearly labeled sample data flags for development.
    """
    __tablename__ = 'navigation_nodes'

    id = db.Column(db.Integer, primary_key=True)
    node_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    building = db.Column(db.String(100), nullable=False, index=True)
    floor = db.Column(db.String(50), nullable=False, default='Ground Floor', index=True)
    category = db.Column(db.String(50), nullable=False, default='Classroom', index=True)
    description = db.Column(db.Text, nullable=True)
    x_coord = db.Column(db.Integer, nullable=False, default=0) # 2D map canvas coordinate X
    y_coord = db.Column(db.Integer, nullable=False, default=0) # 2D map canvas coordinate Y
    photo_url = db.Column(db.String(255), nullable=True)
    is_accessible = db.Column(db.Boolean, default=True, nullable=False)
    is_sample_data = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Graph relationships
    outgoing_edges = db.relationship('NavigationEdge', backref='source_node', lazy=True, foreign_keys='NavigationEdge.source_node_id', cascade="all, delete-orphan")
    incoming_edges = db.relationship('NavigationEdge', backref='target_node', lazy=True, foreign_keys='NavigationEdge.target_node_id', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "node_code": self.node_code,
            "name": self.name,
            "building": self.building,
            "floor": self.floor,
            "category": self.category,
            "description": self.description,
            "x_coord": self.x_coord,
            "y_coord": self.y_coord,
            "photo_url": self.photo_url,
            "is_accessible": self.is_accessible,
            "is_sample_data": self.is_sample_data
        }

    def __repr__(self):
        return f"<NavigationNode {self.node_code}: {self.name}>"


class NavigationEdge(db.Model):
    """Bidirectional / directed connections between navigation nodes for A* and Dijkstra."""
    __tablename__ = 'navigation_edges'

    id = db.Column(db.Integer, primary_key=True)
    source_node_id = db.Column(db.Integer, db.ForeignKey('navigation_nodes.id', ondelete='CASCADE'), nullable=False)
    target_node_id = db.Column(db.Integer, db.ForeignKey('navigation_nodes.id', ondelete='CASCADE'), nullable=False)
    distance_meters = db.Column(db.Float, nullable=False, default=10.0)
    direction_hint = db.Column(db.String(255), nullable=True)
    is_bidirectional = db.Column(db.Boolean, default=True, nullable=False)
    is_sample_data = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "distance_meters": self.distance_meters,
            "direction_hint": self.direction_hint,
            "is_bidirectional": self.is_bidirectional,
            "is_sample_data": self.is_sample_data
        }


class LostFoundItem(db.Model):
    """Lost and Found catalog items with photo embeddings and status tracking."""
    __tablename__ = 'lost_found_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    report_type = db.Column(db.String(10), nullable=False) # 'lost' or 'found'
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Other')
    location_reported = db.Column(db.String(150), nullable=False)
    date_time_reported = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.Text, nullable=False)
    photo_url = db.Column(db.String(255), nullable=True)
    image_feature_vector = db.Column(db.Text, nullable=True) # JSON serialized embedding
    status = db.Column(db.String(20), nullable=False, default='open') # 'open', 'matched', 'claimed', 'closed'
    contact_phone = db.Column(db.String(20), nullable=True)
    claimed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    verified_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    collected_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "reporter_name": self.reporter.full_name if self.reporter else "Unknown",
            "report_type": self.report_type,
            "title": self.title,
            "category": self.category,
            "location_reported": self.location_reported,
            "date_time_reported": self.date_time_reported.strftime('%Y-%m-%d %H:%M') if self.date_time_reported else None,
            "description": self.description,
            "photo_url": self.photo_url,
            "status": self.status,
            "contact_phone": self.contact_phone,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None
        }


class LostFoundMatch(db.Model):
    """AI-suggested similarity pairings between lost and found items."""
    __tablename__ = 'lost_found_matches'

    id = db.Column(db.Integer, primary_key=True)
    lost_item_id = db.Column(db.Integer, db.ForeignKey('lost_found_items.id', ondelete='CASCADE'), nullable=False)
    found_item_id = db.Column(db.Integer, db.ForeignKey('lost_found_items.id', ondelete='CASCADE'), nullable=False)
    similarity_score = db.Column(db.Float, nullable=False) # e.g. 0.87
    status = db.Column(db.String(20), default='suggested') # 'suggested', 'verified', 'rejected'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lost_item = db.relationship('LostFoundItem', foreign_keys=[lost_item_id])
    found_item = db.relationship('LostFoundItem', foreign_keys=[found_item_id])


class CanteenCategory(db.Model):
    """Categorization for canteen food items (e.g. Breakfast, Lunch, Beverages)."""
    __tablename__ = 'canteen_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('CanteenItem', backref='category_rel', lazy=True, cascade="all, delete-orphan")


class CanteenItem(db.Model):
    """Canteen food item with pricing, availability, and real-time inventory."""
    __tablename__ = 'canteen_items'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('canteen_categories.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(8, 2), nullable=False, default=0.00)
    stock_quantity = db.Column(db.Integer, nullable=False, default=50)
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    preparation_time_mins = db.Column(db.Integer, default=10, nullable=False)
    photo_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category_rel.name if self.category_rel else "",
            "name": self.name,
            "description": self.description,
            "price": float(self.price),
            "stock_quantity": self.stock_quantity,
            "is_available": self.is_available,
            "preparation_time_mins": self.preparation_time_mins,
            "photo_url": self.photo_url
        }


class CanteenOrder(db.Model):
    """
    Canteen pre-orders with Teacher-First Priority queue handling and QR code generation.
    """
    __tablename__ = 'canteen_orders'

    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    user_role_at_order = db.Column(db.String(20), nullable=False)
    is_priority = db.Column(db.Boolean, default=False, nullable=False, index=True) # True for teachers
    total_amount = db.Column(db.Numeric(8, 2), nullable=False, default=0.00)
    pickup_time = db.Column(db.DateTime, nullable=False)
    order_status = db.Column(db.String(20), nullable=False, default='placed', index=True)
    # Statuses: 'placed', 'preparing', 'ready', 'collected', 'cancelled', 'refunded'
    payment_status = db.Column(db.String(20), nullable=False, default='paid') # 'pending', 'paid', 'refunded'
    payment_method = db.Column(db.String(30), default='upi_simulation')
    qr_code_path = db.Column(db.String(255), nullable=True)
    refund_reason = db.Column(db.Text, nullable=True)
    collected_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('CanteenOrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "order_code": self.order_code,
            "user_id": self.user_id,
            "customer_name": self.customer.full_name if self.customer else "Unknown",
            "user_role_at_order": self.user_role_at_order,
            "is_priority": self.is_priority,
            "total_amount": float(self.total_amount),
            "pickup_time": self.pickup_time.strftime('%Y-%m-%d %H:%M') if self.pickup_time else None,
            "order_status": self.order_status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "qr_code_path": self.qr_code_path,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
            "items_count": len(self.items)
        }


class CanteenOrderItem(db.Model):
    """Line items for each canteen order."""
    __tablename__ = 'canteen_order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('canteen_orders.id', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('canteen_items.id', ondelete='CASCADE'), nullable=False)
    item_name = db.Column(db.String(150), nullable=False)
    unit_price = db.Column(db.Numeric(8, 2), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    subtotal = db.Column(db.Numeric(8, 2), nullable=False)


class AuditLog(db.Model):
    """Global system audit log for security, administrative actions, and module events."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    module = db.Column(db.String(50), nullable=False) # 'AUTH', 'NAVIGATION', 'LOST_FOUND', 'CANTEEN', 'ADMIN'
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    @classmethod
    def log(cls, action: str, module: str, user_id=None, details: str = None, ip_address: str = None):
        """Standardized helper for recording security and administrative audit events."""
        try:
            entry = cls(
                action=action,
                module=module,
                user_id=user_id,
                details=details,
                ip_address=ip_address
            )
            db.session.add(entry)
            db.session.commit()
            return entry
        except Exception:
            db.session.rollback()
            return None

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else "System / Guest",
            "user_email": self.user.email if self.user else "-",
            "user_role": self.user.role if self.user else "-",
            "action": self.action,
            "module": self.module,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
