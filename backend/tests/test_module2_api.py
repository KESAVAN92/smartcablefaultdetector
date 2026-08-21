from __future__ import annotations


import jwt

def get_auth_headers():
    token = jwt.encode({"email": "admin@t.local", "role": "admin"}, "test-jwt-secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

def create_node(client, *, name: str, node_type: str, x: float, y: float):
    response = client.post(
        "/api/module2/nodes",
        json={
            "name": name,
            "type": node_type,
            "x_coord": x,
            "y_coord": y,
        },
        headers=get_auth_headers()
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def create_edge(
    client,
    *,
    from_node_id: str,
    to_node_id: str,
    length_m: float,
    resistance_per_m: float = 0.01,
    cable_type: str = "XLPE",
):
    response = client.post(
        "/api/module2/edges",
        json={
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "length_m": length_m,
            "resistance_per_m": resistance_per_m,
            "cable_type": cable_type,
        },
        headers=get_auth_headers()
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_node_crud(client):
    created = create_node(client, name="Panel A", node_type="panel", x=120, y=220)

    listed = client.get("/api/module2/nodes")
    assert listed.status_code == 200
    assert listed.get_json()["nodes"][0]["id"] == created["id"]

    fetched = client.get(f"/api/module2/nodes/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["name"] == "Panel A"

    updated = client.put(
        f"/api/module2/nodes/{created['id']}",
        json={
            "name": "Panel A Updated",
            "type": "panel",
            "x_coord": 150,
            "y_coord": 250,
        },
        headers=get_auth_headers()
    )
    assert updated.status_code == 200
    assert updated.get_json()["name"] == "Panel A Updated"
    assert updated.get_json()["x_coord"] == 150

    deleted = client.delete(f"/api/module2/nodes/{created['id']}", headers=get_auth_headers())
    assert deleted.status_code == 204

    missing = client.get(f"/api/module2/nodes/{created['id']}")
    assert missing.status_code == 404


def test_edge_crud(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="Junction B", node_type="junction", x=10, y=10)
    node_c = create_node(client, name="Building C", node_type="building", x=20, y=20)

    created = create_edge(
        client,
        from_node_id=node_a["id"],
        to_node_id=node_b["id"],
        length_m=120,
    )

    listed = client.get("/api/module2/edges")
    assert listed.status_code == 200
    assert listed.get_json()["edges"][0]["id"] == created["id"]

    fetched = client.get(f"/api/module2/edges/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["length_m"] == 120

    updated = client.put(
        f"/api/module2/edges/{created['id']}",
        json={
            "from_node_id": node_b["id"],
            "to_node_id": node_c["id"],
            "length_m": 80,
            "resistance_per_m": 0.02,
            "cable_type": "PVC",
        },
        headers=get_auth_headers()
    )
    assert updated.status_code == 200
    payload = updated.get_json()
    assert payload["from_node_id"] == node_b["id"]
    assert payload["to_node_id"] == node_c["id"]
    assert payload["length_m"] == 80

    deleted = client.delete(f"/api/module2/edges/{created['id']}", headers=get_auth_headers())
    assert deleted.status_code == 204

    missing = client.get(f"/api/module2/edges/{created['id']}")
    assert missing.status_code == 404


def test_duplicate_undirected_edge_is_rejected(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="Junction B", node_type="junction", x=10, y=10)

    create_edge(
        client,
        from_node_id=node_a["id"],
        to_node_id=node_b["id"],
        length_m=120,
    )
    duplicate = client.post(
        "/api/module2/edges",
        json={
            "from_node_id": node_b["id"],
            "to_node_id": node_a["id"],
            "length_m": 120,
            "resistance_per_m": 0.01,
            "cable_type": "XLPE",
        },
        headers=get_auth_headers()
    )

    assert duplicate.status_code == 409


def test_invalid_edge_unknown_node_returns_404(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)

    response = client.post(
        "/api/module2/edges",
        json={
            "from_node_id": node_a["id"],
            "to_node_id": "unknown-node",
            "length_m": 120,
            "resistance_per_m": 0.01,
            "cable_type": "XLPE",
        },
        headers=get_auth_headers()
    )

    assert response.status_code == 404


def test_graph_validation_reports_disconnected_components(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="Junction B", node_type="junction", x=1, y=1)
    node_c = create_node(client, name="Building C", node_type="building", x=2, y=2)
    node_d = create_node(client, name="Junction D", node_type="junction", x=3, y=3)

    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)
    create_edge(client, from_node_id=node_c["id"], to_node_id=node_d["id"], length_m=80)

    response = client.get("/api/module2/graph/validate")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["valid"] is False
    assert len(payload["components"]) == 2


def test_graph_validation_reports_orphan_node(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="Junction B", node_type="junction", x=1, y=1)
    orphan = create_node(client, name="Building C", node_type="building", x=2, y=2)

    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)

    response = client.get("/api/module2/graph/validate")
    assert response.status_code == 200
    payload = response.get_json()
    assert orphan["id"] in payload["orphan_nodes"]
    assert payload["valid"] is False


def test_graph_nearest_exact_node(client):
    node_a = create_node(client, name="A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="B", node_type="junction", x=1, y=1)
    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)

    response = client.get(
        f"/api/module2/graph/nearest?source_node_id={node_a['id']}&distance_m=100"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "nearest_node_id": node_b["id"],
        "edge_id": None,
        "distance_along_edge_m": 0,
    }


def test_graph_nearest_mid_edge(client):
    node_a = create_node(client, name="A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="B", node_type="junction", x=1, y=1)
    edge = create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)

    response = client.get(
        f"/api/module2/graph/nearest?source_node_id={node_a['id']}&distance_m=40"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "nearest_node_id": None,
        "edge_id": edge["id"],
        "distance_along_edge_m": 40,
    }


def test_graph_nearest_multi_edge(client):
    node_a = create_node(client, name="A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="B", node_type="junction", x=1, y=1)
    node_c = create_node(client, name="C", node_type="building", x=2, y=2)
    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)
    edge_bc = create_edge(client, from_node_id=node_b["id"], to_node_id=node_c["id"], length_m=150)

    response = client.get(
        f"/api/module2/graph/nearest?source_node_id={node_a['id']}&distance_m=180"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "nearest_node_id": None,
        "edge_id": edge_bc["id"],
        "distance_along_edge_m": 80,
    }


def test_graph_nearest_beyond_graph_returns_farthest_node(client):
    node_a = create_node(client, name="A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="B", node_type="junction", x=1, y=1)
    node_c = create_node(client, name="C", node_type="building", x=2, y=2)
    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=100)
    create_edge(client, from_node_id=node_b["id"], to_node_id=node_c["id"], length_m=150)

    response = client.get(
        f"/api/module2/graph/nearest?source_node_id={node_a['id']}&distance_m=300"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "nearest_node_id": node_c["id"],
        "edge_id": None,
        "distance_along_edge_m": 0,
    }


def test_graph_export_and_import(client):
    node_a = create_node(client, name="Panel A", node_type="panel", x=0, y=0)
    node_b = create_node(client, name="Junction B", node_type="junction", x=5, y=5)
    create_edge(client, from_node_id=node_a["id"], to_node_id=node_b["id"], length_m=25)

    exported = client.get("/api/module2/graph/export")
    assert exported.status_code == 200
    payload = exported.get_json()
    assert payload["version"] == 1
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1

    replaced = {
        "version": 1,
        "nodes": [
            {
                "id": "A",
                "name": "Panel A",
                "type": "panel",
                "x_coord": 10,
                "y_coord": 10,
            },
            {
                "id": "B",
                "name": "Building B",
                "type": "building",
                "x_coord": 20,
                "y_coord": 20,
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "from_node_id": "A",
                "to_node_id": "B",
                "length_m": 50,
                "resistance_per_m": 0.05,
                "cable_type": "PVC",
            }
        ],
    }
    imported = client.post("/api/module2/graph/import", json=replaced, headers=get_auth_headers())
    assert imported.status_code == 201
    graph = client.get("/api/module2/graph")
    assert graph.status_code == 200
    graph_payload = graph.get_json()
    assert [node["id"] for node in graph_payload["nodes"]] == ["A", "B"]
    assert graph_payload["edges"][0]["id"] == "edge-1"


def test_graph_import_rejects_invalid_payload_without_partial_write(client):
    base_node = create_node(client, name="Panel A", node_type="panel", x=0, y=0)

    invalid_payload = {
        "version": 1,
        "nodes": [
            {
                "id": "A",
                "name": "Panel A",
                "type": "panel",
                "x_coord": 10,
                "y_coord": 10,
            }
        ],
        "edges": [
            {
                "id": "edge-1",
                "from_node_id": "A",
                "to_node_id": "missing-node",
                "length_m": 50,
                "resistance_per_m": 0.05,
                "cable_type": "PVC",
            }
        ],
    }

    response = client.post("/api/module2/graph/import", json=invalid_payload, headers=get_auth_headers())
    assert response.status_code == 422

    listed = client.get("/api/module2/nodes")
    assert listed.status_code == 200
    nodes = listed.get_json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == base_node["id"]
