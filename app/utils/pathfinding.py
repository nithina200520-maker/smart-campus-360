import math
import heapq
from typing import Dict, List, Tuple, Optional, Any
from app.models import NavigationNode, NavigationEdge

def build_graph() -> Tuple[Dict[int, NavigationNode], Dict[int, List[Tuple[int, float, str]]]]:
    """
    Constructs an adjacency list representation of the campus navigation network.
    Returns:
        nodes_dict: Map of node_id -> NavigationNode object
        adjacency: Map of node_id -> list of (neighbor_node_id, distance_meters, direction_hint)
    """
    nodes = NavigationNode.query.filter_by(is_published=True).all()
    edges = NavigationEdge.query.all()

    nodes_dict = {n.id: n for n in nodes}
    adjacency: Dict[int, List[Tuple[int, float, str]]] = {n.id: [] for n in nodes}

    for edge in edges:
        if edge.source_node_id in adjacency and edge.target_node_id in adjacency:
            adjacency[edge.source_node_id].append(
                (edge.target_node_id, edge.distance_meters, edge.direction_hint or "")
            )
            if edge.is_bidirectional:
                adjacency[edge.target_node_id].append(
                    (edge.source_node_id, edge.distance_meters, edge.direction_hint or "")
                )

    return nodes_dict, adjacency

def euclidean_distance(node1: NavigationNode, node2: NavigationNode) -> float:
    """Calculates Euclidean distance heuristic h(n) between 2D map coordinates."""
    dx = node1.x_coord - node2.x_coord
    dy = node1.y_coord - node2.y_coord
    # Conversion scaling factor from canvas pixel units to approximate meters
    return math.sqrt(dx * dx + dy * dy) * 0.1

def dijkstra(start_node_id: int, target_node_id: int) -> Optional[Dict[str, Any]]:
    """
    Standard Dijkstra shortest-path algorithm.
    """
    return find_route(start_node_id, target_node_id, algorithm='dijkstra')

def a_star(start_node_id: int, target_node_id: int) -> Optional[Dict[str, Any]]:
    """
    A* Heuristic shortest-path algorithm.
    """
    return find_route(start_node_id, target_node_id, algorithm='astar')

def find_route(start_node_id: int, target_node_id: int, algorithm: str = 'astar') -> Optional[Dict[str, Any]]:
    """
    Unified pathfinding engine executing A* or Dijkstra on campus graph.
    Returns route data including path nodes, total distance, walk time, step directions, and photo POIs.
    """
    nodes_dict, adjacency = build_graph()

    if start_node_id not in nodes_dict or target_node_id not in nodes_dict:
        return None

    start_node = nodes_dict[start_node_id]
    target_node = nodes_dict[target_node_id]

    # Priority queue: (f_score, current_node_id)
    pq = []
    heapq.heappush(pq, (0.0, start_node_id))

    # Cost from start to current node
    g_score: Dict[int, float] = {node_id: float('inf') for node_id in nodes_dict}
    g_score[start_node_id] = 0.0

    # Came_from map: current_node_id -> (prev_node_id, edge_hint, edge_dist)
    came_from: Dict[int, Tuple[Optional[int], str, float]] = {start_node_id: (None, "", 0.0)}

    visited = set()

    while pq:
        current_f, current_id = heapq.heappop(pq)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id == target_node_id:
            break

        current_node = nodes_dict[current_id]

        for neighbor_id, distance, hint in adjacency.get(current_id, []):
            tentative_g = g_score[current_id] + distance

            if tentative_g < g_score[neighbor_id]:
                came_from[neighbor_id] = (current_id, hint, distance)
                g_score[neighbor_id] = tentative_g
                
                if algorithm == 'astar':
                    neighbor_node = nodes_dict[neighbor_id]
                    h = euclidean_distance(neighbor_node, target_node)
                    f_score = tentative_g + h
                else: # dijkstra
                    f_score = tentative_g

                heapq.heappush(pq, (f_score, neighbor_id))

    if g_score[target_node_id] == float('inf'):
        return None # No connected route found

    # Reconstruct path backwards
    path_node_ids = []
    instructions = []
    curr = target_node_id

    while curr is not None:
        path_node_ids.append(curr)
        prev, hint, dist = came_from[curr]
        if prev is not None:
            prev_node = nodes_dict[prev]
            curr_node = nodes_dict[curr]
            instruction_text = hint if hint else f"Proceed from {prev_node.name} to {curr_node.name}"
            instructions.append({
                "from_node": prev_node.name,
                "to_node": curr_node.name,
                "distance_meters": round(dist, 1),
                "instruction": instruction_text
            })
        curr = prev

    path_node_ids.reverse()
    instructions.reverse()

    # Total distance and walk time (average 80m/min walking pace)
    total_distance_m = round(g_score[target_node_id], 1)
    estimated_minutes = max(1, round(total_distance_m / 80.0, 1))

    # Node detail list with coordinates and photographs
    path_nodes = []
    for nid in path_node_ids:
        node = nodes_dict[nid]
        path_nodes.append({
            "id": node.id,
            "node_code": node.node_code,
            "name": node.name,
            "building": node.building,
            "floor": node.floor,
            "category": node.category,
            "x": node.x_coord,
            "y": node.y_coord,
            "photo_url": node.photo_url or "/static/images/placeholder_node.jpg",
            "is_panoramic": bool(node.is_panoramic),
            "is_sample_data": node.is_sample_data
        })

    return {
        "success": True,
        "algorithm": algorithm.upper(),
        "start_node": nodes_dict[start_node_id].name,
        "target_node": nodes_dict[target_node_id].name,
        "total_distance_meters": total_distance_m,
        "estimated_time_minutes": estimated_minutes,
        "path_nodes": path_nodes,
        "instructions": instructions,
        "node_count": len(path_nodes)
    }
