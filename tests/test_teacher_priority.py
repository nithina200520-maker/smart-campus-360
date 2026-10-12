"""Teacher-First Priority is granted ONLY to verified teacher accounts."""
import app.blueprints.canteen.routes as canteen_routes
from app.models import CanteenCategory, CanteenItem, CanteenOrder
from tests.conftest import login


def _seed_menu(db):
    cat = CanteenCategory(name="Breakfast", display_order=1)
    db.session.add(cat)
    db.session.commit()
    item = CanteenItem(
        category_id=cat.id, name="Masala Dosa", description="Tasty dosa",
        price=45.00, stock_quantity=50, preparation_time_mins=8,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _place_order(client, app, monkeypatch, item):
    # Skip real QR image generation in tests
    monkeypatch.setattr(canteen_routes, "generate_order_qr", lambda order, save_to_disk=True: None)
    with client.session_transaction() as sess:
        sess["canteen_cart"] = {str(item.id): 2}
    return client.post("/canteen/checkout", data={"payment_method": "cash_at_counter"})


def test_model_flag_priority_requires_verification(db, users):
    assert users["teacher_verified"].is_verified_teacher() is True
    assert users["teacher_pending"].is_verified_teacher() is False
    assert users["student"].is_verified_teacher() is False


def test_verified_teacher_order_gets_priority(client, app, users, db, monkeypatch):
    item = _seed_menu(db)
    login(client, "teacher@gechassan.ac.in")
    _place_order(client, app, monkeypatch, item)
    order = CanteenOrder.query.filter_by(user_id=users["teacher_verified"].id).first()
    assert order is not None and order.is_priority is True


def test_unverified_teacher_order_has_no_priority(client, app, users, db, monkeypatch):
    item = _seed_menu(db)
    login(client, "pending.teacher@gechassan.ac.in")
    _place_order(client, app, monkeypatch, item)
    order = CanteenOrder.query.filter_by(user_id=users["teacher_pending"].id).first()
    assert order is not None and order.is_priority is False


def test_student_order_has_no_priority(client, app, users, db, monkeypatch):
    item = _seed_menu(db)
    login(client, "student@gechassan.ac.in")
    _place_order(client, app, monkeypatch, item)
    order = CanteenOrder.query.filter_by(user_id=users["student"].id).first()
    assert order is not None and order.is_priority is False


def test_verification_after_admin_approval_upgrades_next_order(client, app, users, db, monkeypatch, db_session=None):
    item = _seed_menu(db)
    # Pending teacher: first order standard queue
    login(client, "pending.teacher@gechassan.ac.in")
    _place_order(client, app, monkeypatch, item)
    # Main Admin verifies the teacher
    client.get("/auth/logout")
    login(client, "admin@gechassan.ac.in")
    client.post(f"/admin/users/{users['teacher_pending'].id}/verify-teacher")
    assert users["teacher_pending"].is_verified is True
    # Teacher orders again: now priority applies
    client.get("/auth/logout")
    login(client, "pending.teacher@gechassan.ac.in")
    _place_order(client, app, monkeypatch, item)
    orders = CanteenOrder.query.filter_by(user_id=users["teacher_pending"].id).order_by(CanteenOrder.id).all()
    assert len(orders) == 2
    assert orders[0].is_priority is False and orders[1].is_priority is True
