from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from flask import current_app, g


NODE_TYPES = {"panel", "building", "junction"}
GRAPH_EXPORT_VERSION = 1
LAYOUT_ASSET_ID = 1


class Module2Error(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(Module2Error):
    status_code = 404


class ConflictError(Module2Error):
    status_code = 409


class ValidationError(Module2Error):
    status_code = 422


@dataclass(frozen=True)
class NormalizedEdge:
    node_a_id: str
    node_b_id: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    if "module2_db" not in g:
        database_path = current_app.config["DATABASE_PATH"]
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.module2_db = connection
        init_db(connection)
    return g.module2_db


def close_connection(_exception: Exception | None = None) -> None:
    connection = g.pop("module2_db", None)
    if connection is not None:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('panel', 'building', 'junction')),
            x_coord REAL NOT NULL,
            y_coord REAL NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS edges (
            id TEXT PRIMARY KEY,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            node_a_id TEXT NOT NULL,
            node_b_id TEXT NOT NULL,
            length_m REAL NOT NULL CHECK(length_m > 0),
            resistance_per_m REAL NOT NULL CHECK(resistance_per_m > 0),
            cable_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (from_node_id) REFERENCES nodes(id) ON DELETE CASCADE,
            FOREIGN KEY (to_node_id) REFERENCES nodes(id) ON DELETE CASCADE,
            UNIQUE(node_a_id, node_b_id),
            CHECK(from_node_id <> to_node_id)
        );

        CREATE TABLE IF NOT EXISTS layout_assets (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        );
        """
    )
    connection.commit()


def normalize_edge_nodes(from_node_id: str, to_node_id: str) -> NormalizedEdge:
    if from_node_id == to_node_id:
        raise ValidationError("An edge must connect two different nodes.")
    ordered = sorted((from_node_id, to_node_id))
    return NormalizedEdge(node_a_id=ordered[0], node_b_id=ordered[1])


def validate_node_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    node_type = str(payload.get("type", "")).strip().lower()
    if not name:
        raise ValidationError("Node name is required.")
    if node_type not in NODE_TYPES:
        raise ValidationError("Node type must be one of panel, building, or junction.")

    try:
        x_coord = float(payload.get("x_coord"))
        y_coord = float(payload.get("y_coord"))
    except (TypeError, ValueError):
        raise ValidationError("Node coordinates must be valid numbers.") from None

    created_by = payload.get("created_by")
    if created_by is not None:
        created_by = str(created_by).strip() or None

    return {
        "name": name,
        "type": node_type,
        "x_coord": x_coord,
        "y_coord": y_coord,
        "created_by": created_by,
    }


def validate_edge_payload(
    payload: dict[str, Any],
    *,
    require_existing_nodes: bool = True,
) -> dict[str, Any]:
    from_node_id = str(payload.get("from_node_id", "")).strip()
    to_node_id = str(payload.get("to_node_id", "")).strip()
    if not from_node_id or not to_node_id:
        raise ValidationError("Both from_node_id and to_node_id are required.")

    normalized = normalize_edge_nodes(from_node_id, to_node_id)

    try:
        length_m = float(payload.get("length_m"))
        resistance_per_m = float(payload.get("resistance_per_m"))
    except (TypeError, ValueError):
        raise ValidationError("length_m and resistance_per_m must be valid numbers.") from None

    if length_m <= 0:
        raise ValidationError("length_m must be greater than 0.")
    if resistance_per_m <= 0:
        raise ValidationError("resistance_per_m must be greater than 0.")

    cable_type = str(payload.get("cable_type", "")).strip()
    if not cable_type:
        raise ValidationError("cable_type is required.")

    return {
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "node_a_id": normalized.node_a_id,
        "node_b_id": normalized.node_b_id,
        "length_m": length_m,
        "resistance_per_m": resistance_per_m,
        "cable_type": cable_type,
        "require_existing_nodes": require_existing_nodes,
    }


def ensure_node_exists(connection: sqlite3.Connection, node_id: str) -> None:
    row = connection.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Node '{node_id}' was not found.")


def ensure_edge_nodes_exist(connection: sqlite3.Connection, from_node_id: str, to_node_id: str) -> None:
    rows = connection.execute(
        "SELECT id FROM nodes WHERE id IN (?, ?)",
        (from_node_id, to_node_id),
    ).fetchall()
    existing_ids = {row["id"] for row in rows}
    missing_ids = [node_id for node_id in (from_node_id, to_node_id) if node_id not in existing_ids]
    if missing_ids:
        raise NotFoundError(f"Referenced node(s) not found: {', '.join(missing_ids)}.")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_nodes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT id, name, type, x_coord, y_coord, created_by, created_at FROM nodes ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def get_node(connection: sqlite3.Connection, node_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id, name, type, x_coord, y_coord, created_by, created_at FROM nodes WHERE id = ?",
        (node_id,),
    ).fetchone()
    node = row_to_dict(row)
    if node is None:
        raise NotFoundError(f"Node '{node_id}' was not found.")
    return node


def create_node(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    data = validate_node_payload(payload)
    node_id = str(payload.get("id") or uuid4())
    created_at = str(payload.get("created_at") or utc_now_iso())
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO nodes (id, name, type, x_coord, y_coord, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                data["name"],
                data["type"],
                data["x_coord"],
                data["y_coord"],
                data["created_by"],
                created_at,
            ),
        )
    return get_node(connection, node_id)


def update_node(connection: sqlite3.Connection, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = validate_node_payload(payload)
    ensure_node_exists(connection, node_id)
    with transaction(connection):
        connection.execute(
            """
            UPDATE nodes
            SET name = ?, type = ?, x_coord = ?, y_coord = ?, created_by = COALESCE(?, created_by)
            WHERE id = ?
            """,
            (
                data["name"],
                data["type"],
                data["x_coord"],
                data["y_coord"],
                data["created_by"],
                node_id,
            ),
        )
    return get_node(connection, node_id)


def delete_node(connection: sqlite3.Connection, node_id: str) -> None:
    ensure_node_exists(connection, node_id)
    with transaction(connection):
        connection.execute("DELETE FROM nodes WHERE id = ?", (node_id,))


def list_edges(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, from_node_id, to_node_id, length_m, resistance_per_m, cable_type, created_at
        FROM edges
        ORDER BY id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_edge(connection: sqlite3.Connection, edge_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT id, from_node_id, to_node_id, length_m, resistance_per_m, cable_type, created_at
        FROM edges
        WHERE id = ?
        """,
        (edge_id,),
    ).fetchone()
    edge = row_to_dict(row)
    if edge is None:
        raise NotFoundError(f"Edge '{edge_id}' was not found.")
    return edge


def create_edge(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    data = validate_edge_payload(payload)
    ensure_edge_nodes_exist(connection, data["from_node_id"], data["to_node_id"])
    edge_id = str(payload.get("id") or uuid4())
    created_at = str(payload.get("created_at") or utc_now_iso())
    try:
        with transaction(connection):
            connection.execute(
                """
                INSERT INTO edges (
                    id, from_node_id, to_node_id, node_a_id, node_b_id,
                    length_m, resistance_per_m, cable_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge_id,
                    data["from_node_id"],
                    data["to_node_id"],
                    data["node_a_id"],
                    data["node_b_id"],
                    data["length_m"],
                    data["resistance_per_m"],
                    data["cable_type"],
                    created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("An undirected edge between those nodes already exists.") from exc
    return get_edge(connection, edge_id)


def update_edge(connection: sqlite3.Connection, edge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = validate_edge_payload(payload)
    current_edge = get_edge(connection, edge_id)
    ensure_edge_nodes_exist(connection, data["from_node_id"], data["to_node_id"])
    try:
        with transaction(connection):
            connection.execute(
                """
                UPDATE edges
                SET from_node_id = ?, to_node_id = ?, node_a_id = ?, node_b_id = ?,
                    length_m = ?, resistance_per_m = ?, cable_type = ?
                WHERE id = ?
                """,
                (
                    data["from_node_id"],
                    data["to_node_id"],
                    data["node_a_id"],
                    data["node_b_id"],
                    data["length_m"],
                    data["resistance_per_m"],
                    data["cable_type"],
                    edge_id,
                ),
            )
    except sqlite3.IntegrityError as exc:
        if (
            current_edge["from_node_id"] != data["from_node_id"]
            or current_edge["to_node_id"] != data["to_node_id"]
        ):
            raise ConflictError("An undirected edge between those nodes already exists.") from exc
        raise
    return get_edge(connection, edge_id)


def delete_edge(connection: sqlite3.Connection, edge_id: str) -> None:
    get_edge(connection, edge_id)
    with transaction(connection):
        connection.execute("DELETE FROM edges WHERE id = ?", (edge_id,))


def replace_graph(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    version = payload.get("version", GRAPH_EXPORT_VERSION)
    if version != GRAPH_EXPORT_VERSION:
        raise ValidationError(f"Unsupported graph export version: {version}.")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValidationError("Graph import must include 'nodes' and 'edges' arrays.")

    node_ids: set[str] = set()
    normalized_pairs: set[tuple[str, str]] = set()
    validated_nodes: list[dict[str, Any]] = []
    validated_edges: list[dict[str, Any]] = []

    for node_payload in nodes:
        if not isinstance(node_payload, dict):
            raise ValidationError("Each node must be an object.")
        node_id = str(node_payload.get("id", "")).strip()
        if not node_id:
            raise ValidationError("Each imported node requires an id.")
        if node_id in node_ids:
            raise ValidationError(f"Duplicate node id in import: {node_id}.")
        data = validate_node_payload(node_payload)
        validated_nodes.append(
            {
                "id": node_id,
                "created_at": str(node_payload.get("created_at") or utc_now_iso()),
                **data,
            }
        )
        node_ids.add(node_id)

    for edge_payload in edges:
        if not isinstance(edge_payload, dict):
            raise ValidationError("Each edge must be an object.")
        edge_id = str(edge_payload.get("id", "")).strip()
        if not edge_id:
            raise ValidationError("Each imported edge requires an id.")
        data = validate_edge_payload(edge_payload, require_existing_nodes=False)
        if data["from_node_id"] not in node_ids or data["to_node_id"] not in node_ids:
            raise ValidationError(
                f"Imported edge '{edge_id}' references unknown nodes."
            )
        pair = (data["node_a_id"], data["node_b_id"])
        if pair in normalized_pairs:
            raise ValidationError(
                f"Duplicate undirected edge in import: {data['from_node_id']} <-> {data['to_node_id']}."
            )
        normalized_pairs.add(pair)
        validated_edges.append(
            {
                "id": edge_id,
                "created_at": str(edge_payload.get("created_at") or utc_now_iso()),
                **data,
            }
        )

    with transaction(connection):
        connection.execute("DELETE FROM edges")
        connection.execute("DELETE FROM nodes")
        for node in validated_nodes:
            connection.execute(
                """
                INSERT INTO nodes (id, name, type, x_coord, y_coord, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node["id"],
                    node["name"],
                    node["type"],
                    node["x_coord"],
                    node["y_coord"],
                    node["created_by"],
                    node["created_at"],
                ),
            )
        for edge in validated_edges:
            connection.execute(
                """
                INSERT INTO edges (
                    id, from_node_id, to_node_id, node_a_id, node_b_id,
                    length_m, resistance_per_m, cable_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge["id"],
                    edge["from_node_id"],
                    edge["to_node_id"],
                    edge["node_a_id"],
                    edge["node_b_id"],
                    edge["length_m"],
                    edge["resistance_per_m"],
                    edge["cable_type"],
                    edge["created_at"],
                ),
            )


def get_export_payload(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "version": GRAPH_EXPORT_VERSION,
        "nodes": list_nodes(connection),
        "edges": list_edges(connection),
    }


def save_layout_asset(filename: str) -> None:
    connection = get_connection()
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO layout_assets (id, filename, uploaded_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET filename = excluded.filename, uploaded_at = excluded.uploaded_at
            """,
            (LAYOUT_ASSET_ID, filename, utc_now_iso()),
        )


def get_layout_asset() -> dict[str, Any] | None:
    connection = get_connection()
    row = connection.execute(
        "SELECT id, filename, uploaded_at FROM layout_assets WHERE id = ?",
        (LAYOUT_ASSET_ID,),
    ).fetchone()
    return row_to_dict(row)


def get_layout_path(filename: str) -> Path:
    return Path(current_app.config["MODULE2_LAYOUT_DIR"]) / filename
