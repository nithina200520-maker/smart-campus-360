"""
PHASE 3 sample campus data for Smart Campus Navigation.
Government Engineering College, Mosalehosahalli (Hassan), Karnataka.

ALL entries below are TEMPORARY SAMPLE DATA (is_sample_data=True) until the
college uploads verified buildings, room numbers, photographs and routes via
the Main Admin "Manage Map & Photos" screen or the CSV import templates.
No real GEC room numbers or verified routes are invented here.
"""

PHASE3_SAMPLE_NODES = [
    # node_code, name, building, floor, category, description, x, y, photo, is_panoramic
    dict(node_code="NODE_CORRIDOR_A_GF", name="Block A Ground Floor Corridor [SAMPLE]",
         building="Academic Block A", floor="Ground Floor", category="Corridor",
         description="Sample covered corridor connecting ground floor classrooms (replace with real photo).",
         x_coord=330, y_coord=300, photo_url="/static/images/placeholder_node.jpg", is_panoramic=True),
    dict(node_code="NODE_STAIR_A", name="Block A Central Staircase [SAMPLE]",
         building="Academic Block A", floor="Ground Floor", category="Staircase",
         description="Sample central staircase between ground and first floor (replace with real photo).",
         x_coord=440, y_coord=280, photo_url="/static/images/placeholder_node.jpg", is_panoramic=False),
    dict(node_code="NODE_CLASS_A101", name="Sample Classroom A-101 [SAMPLE]",
         building="Academic Block A", floor="Ground Floor", category="Classroom",
         description="Placeholder classroom; real room numbering to be imported by the college.",
         x_coord=290, y_coord=250, photo_url="/static/images/placeholder_node.jpg", is_panoramic=False),
    dict(node_code="NODE_CLASS_A102", name="Sample Classroom A-102 [SAMPLE]",
         building="Academic Block A", floor="1st Floor", category="Classroom",
         description="Placeholder first floor classroom; real room numbering to be imported by the college.",
         x_coord=480, y_coord=150, photo_url="/static/images/placeholder_node.jpg", is_panoramic=False),
    dict(node_code="NODE_CSE_HOD", name="HOD Office - Computer Science & Engineering [SAMPLE]",
         building="Academic Block A", floor="1st Floor", category="HOD Office",
         description="Sample HOD chamber location for CSE department awaiting verified campus data.",
         x_coord=350, y_coord=170, photo_url="/static/images/placeholder_office.jpg", is_panoramic=False),
    dict(node_code="NODE_ECE_HOD", name="HOD Office - Electronics & Communication [SAMPLE]",
         building="Academic Block B", floor="Ground Floor", category="HOD Office",
         description="Sample HOD chamber location for ECE department awaiting verified campus data.",
         x_coord=460, y_coord=440, photo_url="/static/images/placeholder_office.jpg", is_panoramic=False),
    dict(node_code="NODE_HOSTEL_BOYS", name="Boys Hostel Block [SAMPLE]",
         building="Hostel Complex", floor="Ground Floor", category="Hostel",
         description="Sample hostel block node on campus grounds; replace once real data is uploaded.",
         x_coord=860, y_coord=250, photo_url="/static/images/placeholder_gate.jpg", is_panoramic=False),
]

PHASE3_SAMPLE_EDGES = [
    # source_code, target_code, distance, hint
    ("NODE_ADMIN_GF", "NODE_CORRIDOR_A_GF", 70.0, "Enter Block A lobby and proceed straight into the ground floor corridor."),
    ("NODE_CLASS_A101", "NODE_CORRIDOR_A_GF", 15.0, "First door on the left of the corridor."),
    ("NODE_CORRIDOR_A_GF", "NODE_STAIR_A", 20.0, "Walk to the end of the corridor to reach the central staircase."),
    ("NODE_STAIR_A", "NODE_CLASS_A102", 25.0, "Ascend to 1st floor; the classroom is on your right."),
    ("NODE_STAIR_A", "NODE_CSE_HOD", 30.0, "Ascend to 1st floor and turn left towards the department office."),
    ("NODE_STAIR_A", "NODE_CSE_BLOCK", 40.0, "Ascend to 1st floor and continue along the connecting corridor to the labs."),
    ("NODE_CSE_HOD", "NODE_CLASS_A102", 20.0, "Continue straight past the HOD office on the first floor."),
    ("NODE_ECE_BLOCK", "NODE_ECE_HOD", 25.0, "Turn right inside Block B towards the department chamber."),
    ("NODE_CANTEEN", "NODE_HOSTEL_BOYS", 220.0, "Follow the amenities road north-east past the canteen garden to the hostel block."),
]

PHASE3_SAMPLE_FLOOR_PLANS = [
    dict(building="Academic Block A", floor="Ground Floor",
         title="Block A Ground Floor (Sample Blueprint)",
         image_url="/static/images/placeholder_node.jpg", is_sample_data=True),
    dict(building="Academic Block A", floor="1st Floor",
         title="Block A 1st Floor (Sample Blueprint)",
         image_url="/static/images/placeholder_lab.jpg", is_sample_data=True),
]
