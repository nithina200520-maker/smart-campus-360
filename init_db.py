import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from app import create_app
from app.database import db
from app.models import (
    User, NavigationNode, NavigationEdge, CampusFloorPlan,
    CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem,
    LostFoundItem, LostFoundMatch, AuditLog
)
from app.utils.qr_generator import generate_order_qr
from app.utils.image_matcher import extract_image_features

def seed_database():
    """Initializes tables and seeds structured sample data for development."""
    app = create_app()
    with app.app_context():
        print("Creating database schema and tables...")
        db.create_all()

        # Check if users already seeded
        if User.query.first():
            print("Database already contains data. Skipping initial seeding.")
            return

        print("Seeding baseline user accounts across all 5 roles...")
        users = [
            User(
                full_name="College System Administrator",
                email="admin@gechassan.ac.in",
                role="main_admin",
                department="System Administration",
                phone="+91 98450 11001"
            ),
            User(
                full_name="Canteen Supervisor",
                email="canteen@gechassan.ac.in",
                role="canteen_admin",
                department="Campus Canteen Services",
                phone="+91 98450 22002"
            ),
            User(
                full_name="Dr. Ramesh Kumar (Professor)",
                email="teacher@gechassan.ac.in",
                role="teacher",
                department="Computer Science & Engineering",
                phone="+91 98450 33003",
                usn_or_emp_id="EMP-CSE-042",
                designation="Professor & Head",
                is_verified=True,
                is_active=True
            ),
            User(
                full_name="Sneha Patil (Student)",
                email="student@gechassan.ac.in",
                role="student",
                department="Computer Science & Engineering",
                phone="+91 98450 44004",
                usn_or_emp_id="4GH22CS054",
                semester="5th Semester",
                is_verified=True,
                is_active=True
            ),
            User(
                full_name="Anand Sharma (Parent / Visitor)",
                email="visitor@gechassan.ac.in",
                role="visitor",
                department="External Visitor",
                phone="+91 98450 55005",
                purpose_of_visit="Campus Enquiry & Admissions",
                is_verified=True,
                is_active=True
            )
        ]

        passwords = {
            "admin@gechassan.ac.in": "Admin@123",
            "canteen@gechassan.ac.in": "Canteen@123",
            "teacher@gechassan.ac.in": "Teacher@123",
            "student@gechassan.ac.in": "Student@123",
            "visitor@gechassan.ac.in": "Visitor@123"
        }

        for u in users:
            u.set_password(passwords[u.email])
            db.session.add(u)
        db.session.commit()
        print("User accounts successfully created.")

        print("Seeding sample campus navigation nodes [SAMPLE DATA - UNVERIFIED]...")
        sample_nodes = [
            NavigationNode(
                node_code="NODE_MAIN_GATE",
                name="Main Entrance & Security Gate [SAMPLE]",
                building="Campus Perimeter",
                floor="Ground Floor",
                category="Gate",
                description="Campus main entrance gate facing Mosalehosahalli main road.",
                x_coord=80,
                y_coord=360,
                photo_url="/static/images/placeholder_gate.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_ADMIN_GF",
                name="Administrative Block Foyer & Reception [SAMPLE]",
                building="Administrative Block",
                floor="Ground Floor",
                category="Office",
                description="Central enquiry desk, admissions office, and student affairs desk.",
                x_coord=220,
                y_coord=360,
                photo_url="/static/images/placeholder_admin.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_PRINCIPAL_OFFICE",
                name="Principal & Dean Executive Office [SAMPLE]",
                building="Administrative Block",
                floor="Ground Floor",
                category="Office",
                description="Principal's chamber, board meeting room, and academic council hall.",
                x_coord=220,
                y_coord=240,
                photo_url="/static/images/placeholder_office.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_CSE_BLOCK",
                name="Computer Science & Engineering Dept & Labs [SAMPLE]",
                building="Academic Block A",
                floor="1st Floor",
                category="Laboratory",
                description="Department of CSE, AI/ML Research Lab, and Software Engineering Lab.",
                x_coord=400,
                y_coord=220,
                photo_url="/static/images/placeholder_lab.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_ECE_BLOCK",
                name="Electronics & Communication Dept [SAMPLE]",
                building="Academic Block B",
                floor="Ground Floor",
                category="Laboratory",
                description="Department of ECE, VLSI Lab, Microcontroller Lab, and HOD Chamber.",
                x_coord=400,
                y_coord=480,
                photo_url="/static/images/placeholder_lab.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_MECH_WORKSHOP",
                name="Mechanical Engineering Workshops [SAMPLE]",
                building="Mechanical Block",
                floor="Ground Floor",
                category="Laboratory",
                description="Machine shop, CNC laboratory, and foundry practice section.",
                x_coord=560,
                y_coord=520,
                photo_url="/static/images/placeholder_workshop.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_CENTRAL_LIB",
                name="Central Library & Digital Reading Room [SAMPLE]",
                building="Academic Block A",
                floor="2nd Floor",
                category="Library",
                description="Central reference repository, IEEE digital library terminals, and study cubes.",
                x_coord=560,
                y_coord=200,
                photo_url="/static/images/placeholder_library.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_CANTEEN",
                name="Campus Canteen & Cafeteria [SAMPLE]",
                building="Student Amenities Block",
                floor="Ground Floor",
                category="Canteen",
                description="Campus dining hall, automated smart pickup counter, and faculty lounge.",
                x_coord=700,
                y_coord=360,
                photo_url="/static/images/placeholder_canteen.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_SPORTS_GROUND",
                name="College Sports Ground & Pavilion [SAMPLE]",
                building="Athletics Complex",
                floor="Campus Grounds",
                category="Sports Ground",
                description="Athletics track, cricket pitch, basketball court, and physical education room.",
                x_coord=840,
                y_coord=480,
                photo_url="/static/images/placeholder_sports.jpg",
                is_sample_data=True
            ),
            NavigationNode(
                node_code="NODE_AUDITORIUM",
                name="Sir M. Visvesvaraya Seminar Hall [SAMPLE]",
                building="Academic Block A",
                floor="1st Floor",
                category="Auditorium",
                description="250-seater multimedia air-conditioned auditorium for seminars and symposiums.",
                x_coord=700,
                y_coord=200,
                photo_url="/static/images/placeholder_audi.jpg",
                is_sample_data=True
            )
        ]

        for node in sample_nodes:
            db.session.add(node)
        db.session.commit()

        # Connect nodes with sample edges
        node_map = {n.node_code: n.id for n in NavigationNode.query.all()}
        sample_edges = [
            NavigationEdge(
                source_node_id=node_map["NODE_MAIN_GATE"],
                target_node_id=node_map["NODE_ADMIN_GF"],
                distance_meters=140.0,
                direction_hint="Follow the main campus boulevard straight towards the administrative portico.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_ADMIN_GF"],
                target_node_id=node_map["NODE_PRINCIPAL_OFFICE"],
                distance_meters=35.0,
                direction_hint="Take the corridor to your left on the ground floor.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_ADMIN_GF"],
                target_node_id=node_map["NODE_CSE_BLOCK"],
                distance_meters=180.0,
                direction_hint="Exit admin block foyer north, proceed across the quadrangle, and ascend staircase to 1st Floor.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_ADMIN_GF"],
                target_node_id=node_map["NODE_ECE_BLOCK"],
                distance_meters=160.0,
                direction_hint="Exit south towards Academic Block B ground floor.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_CSE_BLOCK"],
                target_node_id=node_map["NODE_CENTRAL_LIB"],
                distance_meters=90.0,
                direction_hint="Take the central staircase up to 2nd Floor and turn right.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_CENTRAL_LIB"],
                target_node_id=node_map["NODE_AUDITORIUM"],
                distance_meters=120.0,
                direction_hint="Walk along the connecting skybridge towards Seminar Hall.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_ADMIN_GF"],
                target_node_id=node_map["NODE_CANTEEN"],
                distance_meters=210.0,
                direction_hint="Follow central pedestrian walkway straight ahead to the Student Amenities Canteen.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_ECE_BLOCK"],
                target_node_id=node_map["NODE_MECH_WORKSHOP"],
                distance_meters=150.0,
                direction_hint="Proceed along the rear avenue towards the Mechanical heavy machinery block.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_CANTEEN"],
                target_node_id=node_map["NODE_SPORTS_GROUND"],
                distance_meters=190.0,
                direction_hint="Head southeast past the canteen garden towards the sports pavilion.",
                is_bidirectional=True
            ),
            NavigationEdge(
                source_node_id=node_map["NODE_CANTEEN"],
                target_node_id=node_map["NODE_AUDITORIUM"],
                distance_meters=130.0,
                direction_hint="Climb external terrace stairs adjacent to canteen portico.",
                is_bidirectional=True
            )
        ]

        for edge in sample_edges:
            db.session.add(edge)
        db.session.commit()
        print("Campus navigation network graph seeded successfully.")

        # Phase 3: additional sample navigation points, connections and floor plans
        from app.utils.sample_navigation_data import (
            PHASE3_SAMPLE_NODES, PHASE3_SAMPLE_EDGES, PHASE3_SAMPLE_FLOOR_PLANS
        )
        for spec in PHASE3_SAMPLE_NODES:
            db.session.add(NavigationNode(**spec, is_accessible=True, is_sample_data=True))
        db.session.commit()
        node_map = {n.node_code: n.id for n in NavigationNode.query.all()}
        for src_code, dst_code, distance, hint in PHASE3_SAMPLE_EDGES:
            db.session.add(NavigationEdge(
                source_node_id=node_map[src_code], target_node_id=node_map[dst_code],
                distance_meters=distance, direction_hint=hint,
                is_bidirectional=True, is_sample_data=True))
        for spec in PHASE3_SAMPLE_FLOOR_PLANS:
            db.session.add(CampusFloorPlan(**spec))
        db.session.commit()
        print("Phase 3 sample classrooms, HOD offices, corridors, staircases and floor plans seeded.")

        print("Seeding Canteen menu categories and items...")
        cat_bf = CanteenCategory(name="South Indian Breakfast", display_order=1)
        cat_lunch = CanteenCategory(name="Lunch & Meals", display_order=2)
        cat_bev = CanteenCategory(name="Beverages", display_order=3)
        cat_snack = CanteenCategory(name="Snacks & Quick Bites", display_order=4)

        db.session.add_all([cat_bf, cat_lunch, cat_bev, cat_snack])
        db.session.commit()

        canteen_items = [
            CanteenItem(
                category_id=cat_bf.id,
                name="Crispy Masala Dosa",
                description="Golden roasted dosa served with potato masala, coconut chutney, and sambar.",
                price=45.00,
                stock_quantity=60,
                preparation_time_mins=8,
                photo_url="/static/images/food_dosa.jpg"
            ),
            CanteenItem(
                category_id=cat_bf.id,
                name="Steamed Idli & Medu Vada Combo",
                description="Two fluffy steamed rice idlis with one crispy medu vada and hot sambar.",
                price=40.00,
                stock_quantity=50,
                preparation_time_mins=5,
                photo_url="/static/images/food_idli.jpg"
            ),
            CanteenItem(
                category_id=cat_lunch.id,
                name="South Indian Thali Meal",
                description="Steamed rice, sambar, rasam, palya (veg curry), curd, papad, and pickle.",
                price=65.00,
                stock_quantity=80,
                preparation_time_mins=10,
                photo_url="/static/images/food_meals.jpg"
            ),
            CanteenItem(
                category_id=cat_lunch.id,
                name="Veg Fried Rice with Gobi Manchurian",
                description="Wok-tossed basmati rice with crunchy vegetables and dry gobi manchurian.",
                price=70.00,
                stock_quantity=45,
                preparation_time_mins=12,
                photo_url="/static/images/food_friedrice.jpg"
            ),
            CanteenItem(
                category_id=cat_bev.id,
                name="Authentic Filter Coffee",
                description="Freshly brewed aromatic South Indian chicory blend with frothy milk.",
                price=15.00,
                stock_quantity=100,
                preparation_time_mins=3,
                photo_url="/static/images/food_coffee.jpg"
            ),
            CanteenItem(
                category_id=cat_bev.id,
                name="Fresh Mint Lemon Juice",
                description="Chilled hydrating lemonade with crushed fresh mint leaves and rock salt.",
                price=20.00,
                stock_quantity=70,
                preparation_time_mins=3,
                photo_url="/static/images/food_juice.jpg"
            ),
            CanteenItem(
                category_id=cat_snack.id,
                name="Hot Samosa with Mint Chutney (2 pcs)",
                description="Crispy golden pastry stuffed with spiced potatoes and green peas.",
                price=25.00,
                stock_quantity=60,
                preparation_time_mins=4,
                photo_url="/static/images/food_samosa.jpg"
            )
        ]

        for item in canteen_items:
            db.session.add(item)
        db.session.commit()
        print("Canteen menu items seeded.")

        print("Seeding sample Lost & Found items...")
        admin_user = User.query.filter_by(role='main_admin').first()
        student_user = User.query.filter_by(role='student').first()

        lf_items = [
            LostFoundItem(
                user_id=student_user.id,
                report_type="lost",
                title="Casio FX-991EX Scientific Calculator [SAMPLE]",
                category="Electronics",
                location_reported="Near Computer Science Lab 2 (1st Floor)",
                date_time_reported=datetime.utcnow() - timedelta(days=1),
                description="Black scientific calculator with yellow sticker on the back cover. Has USN inscribed.",
                contact_phone="+91 98450 44004",
                status="open"
            ),
            LostFoundItem(
                user_id=admin_user.id,
                report_type="found",
                title="Casio Scientific Calculator Found [SAMPLE]",
                category="Electronics",
                location_reported="Central Library Reading Desk #14",
                date_time_reported=datetime.utcnow() - timedelta(hours=18),
                description="Scientific calculator left on desk. Deposited at Security Desk.",
                contact_phone="+91 98450 11001",
                status="open"
            ),
            LostFoundItem(
                user_id=student_user.id,
                report_type="lost",
                title="Blue Steel Water Bottle [SAMPLE]",
                category="Personal Items",
                location_reported="College Canteen Outdoor Tables",
                date_time_reported=datetime.utcnow() - timedelta(days=2),
                description="Milton blue insulated 750ml flask with scratch near base.",
                contact_phone="+91 98450 44004",
                status="open"
            )
        ]

        for lf in lf_items:
            db.session.add(lf)
        db.session.commit()

        # Seed initial suggested AI match between the two calculator entries
        calc_lost = LostFoundItem.query.filter_by(title="Casio FX-991EX Scientific Calculator [SAMPLE]").first()
        calc_found = LostFoundItem.query.filter_by(title="Casio Scientific Calculator Found [SAMPLE]").first()
        if calc_lost and calc_found:
            match = LostFoundMatch(
                lost_item_id=calc_lost.id,
                found_item_id=calc_found.id,
                similarity_score=0.88,
                status="suggested"
            )
            db.session.add(match)
            db.session.commit()

        print("\n=======================================================")
        print("DATABASE INITIALIZATION COMPLETED SUCCESSFULLY!")
        print("College: Government Engineering College, Mosalehosahalli")
        print("Default Accounts:")
        print("  1. Main Admin:    admin@gechassan.ac.in    / Admin@123")
        print("  2. Canteen Admin: canteen@gechassan.ac.in  / Canteen@123")
        print("  3. Teacher:       teacher@gechassan.ac.in  / Teacher@123")
        print("  4. Student:       student@gechassan.ac.in  / Student@123")
        print("  5. Visitor:       visitor@gechassan.ac.in  / Visitor@123")
        print("=======================================================\n")

if __name__ == '__main__':
    seed_database()
