"""
Module 2 Adapter — lives inside modules/module3/adapters/ (Module 3's territory).

TODO-integrate: When Module 2 teammates push branch module-2-graph-engine,
  change USE_REAL_M2_API = True (or set env M2_API_URL).
  The graph_nearest() function will then call their live endpoint.
  No other Module 3 file needs to change.

This file provides:
  • In-memory demo graph (6 nodes, 6 edges) matching the NEC layout image
  • graph_nearest(): BFS/Dijkstra traversal — same algorithm as Module 2's spec
  • get_full_graph(): returns all nodes + edges for frontend rendering
  • validate_graph(): orphan/disconnected component detection
"""

from __future__ import annotations

import os
from typing import Optional

import networkx as nx

# ── Integration flag ──────────────────────────────────────────────────────────
#  Set env var M2_API_URL=http://localhost:5000/api/module2 once M2 is running.
M2_API_URL: Optional[str] = os.environ.get("M2_API_URL")


# ── Demo graph — mirrors the NEC layout image pixel coordinates ───────────────
#  Image dimensions: 1000 × 600 px (CRS.Simple, [y, x] = [lat, lng])

DEMO_NODES: dict[str, dict] = {
    "node-main-panel": {
        "id": "node-main-panel",
        "name": "Main Panel",
        "type": "panel",
        "x_coord": 80.0,
        "y_coord": 300.0,
    },
    "node-admin-block": {
        "id": "node-admin-block",
        "name": "Admin Block",
        "type": "building",
        "x_coord": 300.0,
        "y_coord": 150.0,
    },
    "node-library": {
        "id": "node-library",
        "name": "Library",
        "type": "building",
        "x_coord": 550.0,
        "y_coord": 80.0,
    },
    "node-lab-block": {
        "id": "node-lab-block",
        "name": "Lab Block",
        "type": "building",
        "x_coord": 550.0,
        "y_coord": 360.0,
    },
    "node-hostel-a": {
        "id": "node-hostel-a",
        "name": "Hostel A",
        "type": "building",
        "x_coord": 300.0,
        "y_coord": 460.0,
    },
    "node-sports-complex": {
        "id": "node-sports-complex",
        "name": "Sports Complex",
        "type": "building",
        "x_coord": 820.0,
        "y_coord": 220.0,
    },
}

DEMO_EDGES: dict[str, dict] = {
    "edge-mp-admin": {
        "id": "edge-mp-admin",
        "from_node_id": "node-main-panel",
        "to_node_id": "node-admin-block",
        "length_m": 280.0,
        "resistance_per_m": 0.01,
        "cable_type": "armoured",
    },
    "edge-mp-hostel": {
        "id": "edge-mp-hostel",
        "from_node_id": "node-main-panel",
        "to_node_id": "node-hostel-a",
        "length_m": 220.0,
        "resistance_per_m": 0.01,
        "cable_type": "armoured",
    },
    "edge-admin-lib": {
        "id": "edge-admin-lib",
        "from_node_id": "node-admin-block",
        "to_node_id": "node-library",
        "length_m": 300.0,
        "resistance_per_m": 0.008,
        "cable_type": "standard",
    },
    "edge-lib-lab": {
        "id": "edge-lib-lab",
        "from_node_id": "node-library",
        "to_node_id": "node-lab-block",
        "length_m": 280.0,
        "resistance_per_m": 0.008,
        "cable_type": "standard",
    },
    "edge-lab-sports": {
        "id": "edge-lab-sports",
        "from_node_id": "node-lab-block",
        "to_node_id": "node-sports-complex",
        "length_m": 320.0,
        "resistance_per_m": 0.012,
        "cable_type": "standard",
    },
    "edge-hostel-lab": {
        "id": "edge-hostel-lab",
        "from_node_id": "node-hostel-a",
        "to_node_id": "node-lab-block",
        "length_m": 260.0,
        "resistance_per_m": 0.01,
        "cable_type": "standard",
    },
}


# ── Graph helpers ─────────────────────────────────────────────────────────────

def _build_nx_graph(nodes: dict, edges: dict) -> nx.Graph:
    G = nx.Graph()
    for nid in nodes:
        G.add_node(nid)
    for eid, e in edges.items():
        G.add_edge(
            e["from_node_id"],
            e["to_node_id"],
            edge_id=eid,
            length_m=e["length_m"],
            weight=e["length_m"],
        )
    return G


def _get_nodes_and_edges() -> tuple[dict, dict]:
    """
    Returns (nodes, edges).
    TODO-integrate: if M2_API_URL is set, fetch from M2's /graph endpoint instead.
    """
    if M2_API_URL:
        try:
            import requests
            resp = requests.get(f"{M2_API_URL}/graph", timeout=2)
            data = resp.json()
            nodes = {n["id"]: n for n in data.get("nodes", [])}
            edges = {e["id"]: e for e in data.get("edges", [])}
            if nodes:   # only use real data if non-empty
                return nodes, edges
        except Exception as exc:
            print(f"[m2_adapter] M2 API unavailable ({exc}), using demo graph")
    return DEMO_NODES, DEMO_EDGES


# ── Public API (stable contract — do not change signatures) ───────────────────

def graph_nearest(source_node_id: str, distance_m: float) -> dict:
    """
    Walk the graph outward from source_node_id accumulating edge lengths
    until distance_m is consumed.

    Returns:
        {
          "nearest_node_id": str,
          "edge_id": str | None,           # None if fault lands exactly on a node
          "distance_along_edge_m": float | None,
          "beyond_graph": bool,            # True if distance exceeds entire graph
        }
    """
    nodes, edges = _get_nodes_and_edges()
    G = _build_nx_graph(nodes, edges)

    if source_node_id not in G:
        raise ValueError(f"source_node_id '{source_node_id}' not in graph")

    if distance_m <= 0:
        return {
            "nearest_node_id": source_node_id,
            "edge_id": None,
            "distance_along_edge_m": None,
            "beyond_graph": False,
        }

    try:
        path_lengths = dict(
            nx.single_source_dijkstra_path_length(G, source_node_id, weight="weight")
        )
        path_nodes = dict(
            nx.single_source_dijkstra_path(G, source_node_id, weight="weight")
        )
    except nx.NetworkXError as exc:
        raise ValueError(str(exc))

    # Sorted list of (node_id, cumulative_dist) reachable from source
    sorted_nodes = sorted(path_lengths.items(), key=lambda x: x[1])

    for node_id, node_dist in sorted_nodes:
        if node_id == source_node_id:
            continue
        path = path_nodes[node_id]
        if len(path) < 2:
            continue

        prev_id = path[-2]
        curr_id = path[-1]
        edge_data = G.get_edge_data(prev_id, curr_id)
        if not edge_data:
            continue

        dist_to_prev = path_lengths.get(prev_id, 0.0)

        if distance_m <= node_dist:
            offset = distance_m - dist_to_prev
            if offset <= 0:
                return {
                    "nearest_node_id": prev_id,
                    "edge_id": None,
                    "distance_along_edge_m": None,
                    "beyond_graph": False,
                }
            return {
                "nearest_node_id": prev_id,
                "edge_id": edge_data["edge_id"],
                "distance_along_edge_m": round(offset, 3),
                "beyond_graph": False,
            }

    # Distance exceeds entire graph
    farthest = sorted_nodes[-1][0] if sorted_nodes else source_node_id
    return {
        "nearest_node_id": farthest,
        "edge_id": None,
        "distance_along_edge_m": None,
        "beyond_graph": True,
    }


def get_full_graph() -> dict:
    """Return all nodes and edges for frontend rendering."""
    nodes, edges = _get_nodes_and_edges()
    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }


def validate_graph() -> dict:
    """Detect orphan nodes and disconnected components."""
    nodes, edges = _get_nodes_and_edges()
    G = _build_nx_graph(nodes, edges)
    components = list(nx.connected_components(G))
    orphans = [nid for nid, deg in G.degree() if deg == 0]
    return {
        "is_connected": len(components) <= 1 and len(orphans) == 0,
        "component_count": len(components),
        "orphan_nodes": orphans,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }
