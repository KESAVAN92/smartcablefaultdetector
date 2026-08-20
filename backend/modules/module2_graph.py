from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

import networkx as nx

from .module2_store import (
    NotFoundError,
    get_export_payload,
    list_edges,
    list_nodes,
)


@dataclass(frozen=True)
class TraversalEntry:
    node_id: str
    distance_m: float
    path: tuple[str, ...]
    predecessor_id: str | None
    via_edge_id: str | None


class GraphService:
    def __init__(self, connection) -> None:
        self.connection = connection

    def build_graph(self) -> nx.Graph:
        graph = nx.Graph()
        for node in list_nodes(self.connection):
            graph.add_node(
                node["id"],
                name=node["name"],
                type=node["type"],
                x_coord=node["x_coord"],
                y_coord=node["y_coord"],
            )
        for edge in list_edges(self.connection):
            graph.add_edge(
                edge["from_node_id"],
                edge["to_node_id"],
                id=edge["id"],
                length_m=edge["length_m"],
                resistance_per_m=edge["resistance_per_m"],
                cable_type=edge["cable_type"],
            )
        return graph

    def get_graph(self) -> dict[str, Any]:
        return {
            "nodes": list_nodes(self.connection),
            "edges": list_edges(self.connection),
        }

    def export_graph(self) -> dict[str, Any]:
        return get_export_payload(self.connection)

    def validate_graph(self) -> dict[str, Any]:
        graph = self.build_graph()
        orphan_nodes = sorted(
            node_id for node_id, degree in graph.degree() if degree == 0
        )
        if graph.number_of_nodes() == 0:
            components: list[list[str]] = []
        else:
            components = [
                sorted(component)
                for component in nx.connected_components(graph)
            ]
            components.sort(key=lambda component: (component[0], len(component)))
        valid = not orphan_nodes and len(components) <= 1
        return {
            "valid": valid,
            "orphan_nodes": orphan_nodes,
            "components": components,
        }

    def get_nearest_position(self, source_node_id: str, distance_m: float) -> dict[str, Any]:
        if distance_m < 0:
            raise ValueError("distance_m must be greater than or equal to 0.")

        graph = self.build_graph()
        if source_node_id not in graph:
            raise NotFoundError(f"Node '{source_node_id}' was not found.")
        if distance_m == 0:
            return {
                "nearest_node_id": source_node_id,
                "edge_id": None,
                "distance_along_edge_m": 0,
            }

        entries = self._build_shortest_path_tree(graph, source_node_id)
        ordered_entries = sorted(
            entries.values(),
            key=lambda entry: (entry.distance_m, entry.path),
        )

        for entry in ordered_entries:
            if entry.node_id == source_node_id:
                continue
            if abs(entry.distance_m - distance_m) < 1e-9:
                return {
                    "nearest_node_id": entry.node_id,
                    "edge_id": None,
                    "distance_along_edge_m": 0,
                }

        candidate_edges: list[tuple[float, tuple[str, ...], TraversalEntry]] = []
        for entry in ordered_entries:
            if entry.predecessor_id is None or entry.via_edge_id is None:
                continue
            predecessor = entries[entry.predecessor_id]
            if predecessor.distance_m < distance_m < entry.distance_m:
                candidate_edges.append((entry.distance_m, entry.path, entry))

        if candidate_edges:
            _, _, selected = min(candidate_edges, key=lambda item: (item[0], item[1]))
            predecessor = entries[selected.predecessor_id]
            return {
                "nearest_node_id": None,
                "edge_id": selected.via_edge_id,
                "distance_along_edge_m": distance_m - predecessor.distance_m,
            }

        farthest = max(ordered_entries, key=lambda entry: (entry.distance_m, entry.path))
        return {
            "nearest_node_id": farthest.node_id,
            "edge_id": None,
            "distance_along_edge_m": 0,
        }

    def _build_shortest_path_tree(
        self,
        graph: nx.Graph,
        source_node_id: str,
    ) -> dict[str, TraversalEntry]:
        distances: dict[str, float] = {source_node_id: 0.0}
        paths: dict[str, tuple[str, ...]] = {source_node_id: (source_node_id,)}
        predecessors: dict[str, str | None] = {source_node_id: None}
        via_edges: dict[str, str | None] = {source_node_id: None}
        heap: list[tuple[float, tuple[str, ...], str]] = [(0.0, (source_node_id,), source_node_id)]

        while heap:
            current_distance, current_path, node_id = heapq.heappop(heap)
            if current_distance > distances[node_id] + 1e-9:
                continue
            if current_path != paths[node_id]:
                continue

            neighbors = sorted(graph.neighbors(node_id))
            for neighbor_id in neighbors:
                edge_data = graph.get_edge_data(node_id, neighbor_id)
                next_distance = current_distance + float(edge_data["length_m"])
                next_path = current_path + (neighbor_id,)
                known_distance = distances.get(neighbor_id)
                should_update = known_distance is None or next_distance < known_distance - 1e-9
                if not should_update and known_distance is not None and abs(next_distance - known_distance) < 1e-9:
                    should_update = next_path < paths[neighbor_id]
                if should_update:
                    distances[neighbor_id] = next_distance
                    paths[neighbor_id] = next_path
                    predecessors[neighbor_id] = node_id
                    via_edges[neighbor_id] = edge_data["id"]
                    heapq.heappush(heap, (next_distance, next_path, neighbor_id))

        return {
            node_id: TraversalEntry(
                node_id=node_id,
                distance_m=distances[node_id],
                path=paths[node_id],
                predecessor_id=predecessors[node_id],
                via_edge_id=via_edges[node_id],
            )
            for node_id in distances
        }
