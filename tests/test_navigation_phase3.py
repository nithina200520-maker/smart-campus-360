"""
PHASE 3 TESTS - Smart Campus Navigation module.
Covers: A*/Dijkstra graph routing, street-view connections API, floor plans,
Main Admin map management (nodes/edges/plans), CSV import templates & bulk
import, panoramic flags and RBAC guards. Runs only against the throwaway
test database (see conftest.py) - never the real campus data.
"""
import io
import pytest
from tests.conftest import login, TEST_PASSWORD
from app.models import NavigationNode, NavigationEdge, CampusFloorPlan, AuditLog
from app.utils.pathfinding import find_route


@pytest.fixture
def nav_graph(db):
    """Small deterministic campus graph with hints, a directed edge and a floor plan."""
    gate = NavigationNode(node_code="T_GATE", name="Main Gate", building="Perimeter",
                          floor="Ground Floor", category="Gate", x_coord=0, y_coord=100)
    admin = NavigationNode(node_code="T_ADMIN", name="Admin Office", building="Admin Block",
                           floor="Ground Floor", category="Office", x_coord=100, y_coord=100)
    corridor = NavigationNode(node_code="T_CORR", name="Block A Corridor", building="Academic Block A",
                              floor="Ground Floor", category="Corridor", x_coord=200, y_coord=100,
                              photo_url="/static/images/placeholder_node.jpg", is_panoramic=True)
    stair = NavigationNode(node_code="T_STAIR", name="Block A Staircase", building="Academic Block A",
                           floor="Ground Floor", category="Staircase", x_coord=250, y_coord=100)
    hod = NavigationNode(node_code="T_HOD", name="HOD Office CSE", building="Academic Block A",
                         floor="1st Floor", category="HOD Office", x_coord=300, y_coord=50)
    orphan = NavigationNode(node_code="T_ORPHAN", name="Disconnected Shed", building="Far Corner",
                            floor="Ground Floor", category="Landmark", x_coord=900, y_coord=900)
    db.session.add_all([gate, admin, corridor, stair, hod, orphan])
    db.session.commit()

    db.session.add_all([
        NavigationEdge(source_node_id=gate.id, target_node_id=admin.id, distance_meters=50,
                       direction_hint="Straight along the boulevard", is_bidirectional=True, is_sample_data=True),
        NavigationEdge(source_node_id=admin.id, target_node_id=corridor.id, distance_meters=40,
                       direction_hint="Turn left into Block A", is_bidirectional=True, is_sample_data=True),
        NavigationEdge(source_node_id=corridor.id, target_node_id=stair.id, distance_meters=20,
                       direction_hint="End of corridor", is_bidirectional=True, is_sample_data=True),
        NavigationEdge(source_node_id=stair.id, target_node_id=hod.id, distance_meters=30,
                       direction_hint="Upstairs, turn right", is_bidirectional=False, is_sample_data=True),
    ])
    db.session.commit()

    plan = CampusFloorPlan(building="Academic Block A", floor="Ground Floor",
                           title="Block A GF Plan", image_url="/static/images/placeholder_audi.jpg",
                           is_sample_data=True)
    db.session.add(plan)
    db.session.commit()
    return {"gate": gate, "admin": admin, "corridor": corridor, "stair": stair,
            "hod": hod, "orphan": orphan, "plan": plan}


# ---------------------------------------------------------------- pathfinding
class TestRouteCalculation:
    def test_astar_follows_configured_edges_only(self, app, nav_graph):
        with app.app_context():
            route = find_route(nav_graph["gate"].id, nav_graph["hod"].id, algorithm='astar')
        assert route is not None
        assert route["algorithm"] == "ASTAR"
        codes = [n["node_code"] for n in route["path_nodes"]]
        assert codes == ["T_GATE", "T_ADMIN", "T_CORR", "T_STAIR", "T_HOD"]
        assert route["total_distance_meters"] == pytest.approx(140.0)

    def test_dijkstra_matches_astar_distance(self, app, nav_graph):
        with app.app_context():
            a = find_route(nav_graph["gate"].id, nav_graph["hod"].id, algorithm='astar')
            d = find_route(nav_graph["gate"].id, nav_graph["hod"].id, algorithm='dijkstra')
        assert a["total_distance_meters"] == d["total_distance_meters"]
        assert a["path_nodes"][-1]["node_code"] == d["path_nodes"][-1]["node_code"]

    def test_unconnected_destination_returns_none(self, app, nav_graph):
        with app.app_context():
            assert find_route(nav_graph["gate"].id, nav_graph["orphan"].id) is None

    def test_direction_hints_and_photos_in_route_payload(self, app, nav_graph):
        with app.app_context():
            route = find_route(nav_graph["gate"].id, nav_graph["hod"].id)
        assert all(step["instruction"] for step in route["instructions"])
        corridor = next(n for n in route["path_nodes"] if n["node_code"] == "T_CORR")
        assert corridor["is_panoramic"] is True
        assert corridor["photo_url"].endswith("placeholder_node.jpg")

    def test_directed_edge_not_traversable_in_reverse(self, app, nav_graph):
        """Staircase -> HOD is one-way; walking back from HOD must fail."""
        with app.app_context():
            assert find_route(nav_graph["hod"].id, nav_graph["stair"].id) is None

    def test_route_api_endpoints(self, client, nav_graph):
        resp = client.post("/navigation/api/route", json={
            "start_node_id": nav_graph["gate"].id,
            "target_node_id": nav_graph["corridor"].id, "algorithm": "dijkstra"})
        data = resp.get_json()
        assert resp.status_code == 200 and data["success"] and data["algorithm"] == "DIJKSTRA"
        bad = client.post("/navigation/api/route", json={
            "start_node_id": nav_graph["gate"].id, "target_node_id": nav_graph["gate"].id})
        assert bad.status_code == 400


# --------------------------------------------------- street-view connections
class TestPhotoConnections:
    def test_bidirectional_neighbors_listed(self, client, nav_graph):
        resp = client.get(f"/navigation/api/node/{nav_graph['corridor'].id}/connections")
        data = resp.get_json()
        assert data["success"]
        names = {c["node"]["node_code"] for c in data["connections"]}
        assert {"T_ADMIN", "T_STAIR"} <= names
        assert all(c["direction_hint"] and c["distance_meters"] > 0 for c in data["connections"])

    def test_directed_incoming_edge_not_shown(self, client, nav_graph):
        """HOD's only edge is an incoming one-way: it must not offer a walkable arrow."""
        data = client.get(f"/navigation/api/node/{nav_graph['hod'].id}/connections").get_json()
        assert data["connection_count"] == 0

    def test_unknown_node_404(self, client, nav_graph):
        assert client.get("/navigation/api/node/99999/connections").status_code == 404

    def test_visitor_can_use_public_navigation(self, client, users, nav_graph):
        login(client, "visitor@gechassan.ac.in")
        page = client.get("/navigation/")
        assert page.status_code == 200
        api = client.get(f"/navigation/api/node/{nav_graph['corridor'].id}/connections")
        assert api.status_code == 200


# ------------------------------------------------------------ map page data
class TestMapPage:
    def test_index_shows_floor_plans_and_samples(self, client, nav_graph):
        html = client.get("/navigation/").get_data(as_text=True)
        assert "Digital Map &amp; Floor Plans" in html
        assert "Block A GF Plan" in html            # floor plan selector option
        assert "btnFullscreen" in html              # full-screen viewer control
        assert "svConnections" in html              # directional arrow strip
        assert "Start Street-View Walkthrough" in html

    def test_category_and_building_filters_populated(self, client, nav_graph):
        html = client.get("/navigation/").get_data(as_text=True)
        assert "HOD Office" in html and "Staircase" in html
        assert "Academic Block A" in html


# ---------------------------------------------------- Main Admin map manager
class TestAdminMapManagement:
    def test_page_requires_main_admin(self, client, users, nav_graph):
        login(client, "student@gechassan.ac.in")
        resp = client.get("/admin/navigation/manage")
        assert resp.status_code in (301, 302)  # redirected away by role_required

    def test_create_node_with_panoramic_flag(self, client, users, db, nav_graph):
        login(client, "admin@gechassan.ac.in")
        resp = client.post("/admin/navigation/node/create", data={
            "node_code": "NODE_NEW_ROOM", "name": "Sample Lab Room [SAMPLE]",
            "building": "Academic Block A", "floor": "2nd Floor", "category": "Laboratory",
            "x_coord": 500, "y_coord": 300, "is_panoramic": "on", "is_accessible": "on",
            "is_sample_data": "on"})
        assert resp.status_code == 302
        with client.application.app_context():
            node = NavigationNode.query.filter_by(node_code="NODE_NEW_ROOM").first()
            assert node and node.is_panoramic and node.is_sample_data
            assert AuditLog.query.filter_by(action='NAV_NODE_CREATED').count() == 1

    def test_duplicate_node_code_rejected(self, client, users, nav_graph):
        login(client, "admin@gechassan.ac.in")
        client.post("/admin/navigation/node/create", data={
            "node_code": "T_GATE", "name": "Dupe", "building": "X", "floor": "Ground Floor", "category": "Gate"})
        with client.application.app_context():
            assert NavigationNode.query.filter_by(name="Dupe").first() is None

    def test_create_and_delete_edge(self, client, users, db, nav_graph):
        login(client, "admin@gechassan.ac.in")
        resp = client.post("/admin/navigation/edge/create", data={
            "source_node_id": nav_graph["gate"].id, "target_node_id": nav_graph["stair"].id,
            "distance_meters": 300, "direction_hint": "Service road", "is_bidirectional": "on"})
        assert resp.status_code == 302
        with client.application.app_context():
            edge = NavigationEdge.query.filter_by(source_node_id=nav_graph["gate"].id,
                                                  target_node_id=nav_graph["stair"].id).first()
            assert edge is not None
            edge_id = edge.id
            resp2 = client.post(f"/admin/navigation/edge/{edge_id}/delete")
            assert resp2.status_code == 302
            assert NavigationEdge.query.get(edge_id) is None

    def test_floor_plan_upload_and_delete(self, client, users, db, nav_graph):
        login(client, "admin@gechassan.ac.in")
        client.post("/admin/navigation/floorplan/create", data={
            "building": "Library Block", "floor": "1st Floor", "title": "Reading Hall Plan",
            "image_url": "/static/images/placeholder_library.jpg"})
        with client.application.app_context():
            plan = CampusFloorPlan.query.filter_by(title="Reading Hall Plan").first()
            assert plan is not None
            plan_id = plan.id
        client.post(f"/admin/navigation/floorplan/{plan_id}/delete")
        with client.application.app_context():
            assert CampusFloorPlan.query.get(plan_id) is None

    def test_delete_node_removes_connected_edges(self, client, users, db, nav_graph):
        login(client, "admin@gechassan.ac.in")
        client.post(f"/admin/navigation/node/{nav_graph['corridor'].id}/delete")
        with client.application.app_context():
            assert NavigationNode.query.get(nav_graph["corridor"].id) is None
            assert NavigationEdge.query.filter(
                (NavigationEdge.source_node_id == nav_graph["corridor"].id) |
                (NavigationEdge.target_node_id == nav_graph["corridor"].id)).count() == 0


# ------------------------------------------------------------ CSV data import
class TestDataImport:
    def test_templates_download(self, client, users):
        login(client, "admin@gechassan.ac.in")
        for kind, header in [("nodes", "node_code,name,building"),
                             ("edges", "source_node_code,target_node_code"),
                             ("floorplans", "building,floor,title")]:
            resp = client.get(f"/admin/navigation/template/{kind}")
            assert resp.status_code == 200
            assert "text/csv" in resp.content_type
            assert header in resp.get_data(as_text=True)

    def test_nodes_and_edges_csv_import(self, client, users, db, nav_graph):
        login(client, "admin@gechassan.ac.in")
        nodes_csv = io.BytesIO(
            ("node_code,name,building,floor,category,x_coord,y_coord,is_sample_data\r\n"
             "IMP_ROOM_1,Imported Room 1,Import Block,Ground Floor,Classroom,10,20,False\r\n"
             "IMP_ROOM_2,Imported Room 2,Import Block,1st Floor,Classroom,30,40,True\r\n"
             "T_GATE,Duplicate Code Ignored,Perimeter,Ground Floor,Gate,0,0,True\r\n").encode())
        resp = client.post("/admin/navigation/import", data={
            "kind": "nodes", "csv_file": (nodes_csv, "nodes.csv")},
            content_type="multipart/form-data", follow_redirects=True)
        assert "2 nodes record(s) created" in resp.get_data(as_text=True)
        with client.application.app_context():
            assert NavigationNode.query.filter_by(node_code="IMP_ROOM_1").first() is not None
            # Fixture seeded 6 nodes; 2 new imported, duplicate code skipped => 8 total
            assert NavigationNode.query.count() == 8

        edges_csv = io.BytesIO(
            ("source_node_code,target_node_code,distance_meters,direction_hint,is_bidirectional\r\n"
             "IMP_ROOM_1,IMP_ROOM_2,25,Up the stairs,True\r\n").encode())
        client.post("/admin/navigation/import", data={
            "kind": "edges", "csv_file": (edges_csv, "edges.csv")},
            content_type="multipart/form-data", follow_redirects=True)
        with client.application.app_context():
            a = NavigationNode.query.filter_by(node_code="IMP_ROOM_1").first()
            b = NavigationNode.query.filter_by(node_code="IMP_ROOM_2").first()
            assert NavigationEdge.query.filter_by(source_node_id=a.id, target_node_id=b.id).first() is not None
            assert AuditLog.query.filter_by(action='NAV_DATA_IMPORTED').count() >= 1

    def test_import_requires_main_admin(self, client, users):
        login(client, "student@gechassan.ac.in")
        resp = client.post("/admin/navigation/import", data={
            "kind": "nodes", "csv_file": (io.BytesIO(b"node_code,name,building\nX,Y,Z\n"), "n.csv")},
            content_type="multipart/form-data")
        assert resp.status_code in (301, 302)  # blocked by role guard
