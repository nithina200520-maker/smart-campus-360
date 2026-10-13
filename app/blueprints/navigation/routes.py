from flask import render_template, request, jsonify, flash, redirect, url_for
from app.blueprints.navigation import navigation_bp
from app.models import NavigationNode, NavigationEdge, CampusFloorPlan
from app.utils.auth_helpers import get_current_user, role_required
from app.utils.pathfinding import find_route

@navigation_bp.route('/')
def index():
    """Module 1: Interactive Campus Navigator foundation."""
    user = get_current_user()
    # Phase 8: only Main-Admin-published locations appear on the public map
    nodes = NavigationNode.query.filter_by(is_published=True).order_by(NavigationNode.building.asc(), NavigationNode.name.asc()).all()
    categories = sorted(list(set(n.category for n in nodes)))
    buildings = sorted(list(set(n.building for n in nodes)))
    floor_plans = CampusFloorPlan.query.order_by(CampusFloorPlan.building.asc()).all()

    return render_template(
        'navigation/index.html',
        user=user,
        nodes=nodes,
        categories=categories,
        buildings=buildings,
        floor_plans=floor_plans
    )

@navigation_bp.route('/api/nodes', methods=['GET'])
def get_nodes_api():
    """API endpoint providing all navigation nodes for map canvas rendering."""
    nodes = NavigationNode.query.filter_by(is_published=True).all()
    return jsonify({
        "success": True,
        "nodes": [n.to_dict() for n in nodes]
    })

@navigation_bp.route('/api/route', methods=['POST'])
def calculate_route_api():
    """
    Computes optimal path between start and destination nodes
    using A* or Dijkstra graph traversal.
    """
    data = request.get_json() or {}
    start_id = data.get('start_node_id')
    target_id = data.get('target_node_id')
    algorithm = data.get('algorithm', 'astar').lower()

    if not start_id or not target_id:
        return jsonify({"success": False, "error": "Start and destination nodes are required."}), 400

    if start_id == target_id:
        return jsonify({"success": False, "error": "Start and destination cannot be identical."}), 400

    route_result = find_route(int(start_id), int(target_id), algorithm=algorithm)
    if not route_result:
        return jsonify({"success": False, "error": "No viable path could be calculated between these two locations."}), 404

    return jsonify(route_result)

@navigation_bp.route('/api/node/<int:node_id>', methods=['GET'])
def get_node_detail_api(node_id):
    """Fetches single node details with street-view / point of interest photo."""
    node = NavigationNode.query.filter_by(id=node_id, is_published=True).first_or_404()
    return jsonify({
        "success": True,
        "node": node.to_dict()
    })

@navigation_bp.route('/api/node/<int:node_id>/connections', methods=['GET'])
def get_node_connections_api(node_id):
    """
    Phase 3: Street-view graph walker.
    Returns every node walkable-connected to this node (following configured
    bidirectional/directed edges) with direction hints, distance and photograph
    references so the viewer can move photo-to-photo like Google Street View.
    """
    node = NavigationNode.query.filter_by(id=node_id, is_published=True).first_or_404()
    edges = NavigationEdge.query.filter(
        ((NavigationEdge.source_node_id == node_id) & NavigationEdge.is_bidirectional) |
        ((NavigationEdge.target_node_id == node_id) & NavigationEdge.is_bidirectional) |
        ((NavigationEdge.source_node_id == node_id) & ~NavigationEdge.is_bidirectional)
    ).all()

    connections = []
    seen = set()
    for edge in edges:
        other_id = edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
        if other_id == node.id or other_id in seen:
            continue
        # Phase 8: unpublished neighbours are not exposed on the public walker
        other = NavigationNode.query.filter_by(id=other_id, is_published=True).first()
        if not other:
            continue
        seen.add(other.id)
        connections.append({
            "node": other.to_dict(),
            "edge_id": edge.id,
            "distance_meters": edge.distance_meters,
            "direction_hint": edge.direction_hint or "Continue towards",
            "traversable_back": bool(edge.is_bidirectional)
        })

    return jsonify({
        "success": True,
        "source_node": node.to_dict(),
        "connections": connections,
        "connection_count": len(connections)
    })
