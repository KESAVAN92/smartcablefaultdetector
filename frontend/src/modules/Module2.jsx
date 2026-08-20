import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000";
const MODULE2_BASE = `${API_BASE}/api/module2`;
const EMPTY_EDGE_FORM = {
  length_m: "100",
  resistance_per_m: "0.01",
  cable_type: "XLPE"
};
const EMPTY_NEAREST_FORM = {
  source_node_id: "",
  distance_m: "0"
};

function getApiUrl(path) {
  return `${MODULE2_BASE}${path}`;
}

function getAssetUrl(path) {
  if (!path) {
    return null;
  }
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

async function parseJsonResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.error || `Request failed with status ${response.status}`);
  }
  return data;
}

function formatCoordinate(value) {
  return Number(value).toFixed(1);
}

export default function Module2() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [layoutImageUrl, setLayoutImageUrl] = useState(null);
  const [imageMeta, setImageMeta] = useState({ width: 1200, height: 800 });
  const [pendingNode, setPendingNode] = useState(null);
  const [nodeForm, setNodeForm] = useState({ name: "", type: "junction" });
  const [selectedNodeIds, setSelectedNodeIds] = useState([]);
  const [edgeForm, setEdgeForm] = useState(EMPTY_EDGE_FORM);
  const [validation, setValidation] = useState(null);
  const [nearestForm, setNearestForm] = useState(EMPTY_NEAREST_FORM);
  const [nearestResult, setNearestResult] = useState(null);
  const [importPayload, setImportPayload] = useState("");
  const [exportPayload, setExportPayload] = useState("");
  const [statusMessage, setStatusMessage] = useState("Loading graph workspace...");
  const [errorMessage, setErrorMessage] = useState("");

  const nodeMap = useMemo(
    () => Object.fromEntries(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes]
  );

  async function loadGraph() {
    const [graphResponse, layoutResponse, validationResponse] = await Promise.all([
      fetch(getApiUrl("/graph")),
      fetch(getApiUrl("/layout-image")),
      fetch(getApiUrl("/graph/validate"))
    ]);

    const graphData = await parseJsonResponse(graphResponse);
    const layoutData = await parseJsonResponse(layoutResponse);
    const validationData = await parseJsonResponse(validationResponse);

    setGraph(graphData);
    setValidation(validationData);
    setLayoutImageUrl(getAssetUrl(layoutData.layout_image_url));
    setStatusMessage("Graph workspace ready.");
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        setErrorMessage("");
        await loadGraph();
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error.message);
          setStatusMessage("Unable to load Module 2 data.");
        }
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshGraph(successMessage) {
    try {
      setErrorMessage("");
      await loadGraph();
      if (successMessage) {
        setStatusMessage(successMessage);
      }
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  function handleImageLoad(event) {
    setImageMeta({
      width: event.currentTarget.naturalWidth || 1200,
      height: event.currentTarget.naturalHeight || 800
    });
  }

  function handleCanvasClick(event) {
    if (!layoutImageUrl) {
      return;
    }
    const image = event.currentTarget.querySelector("img");
    if (!image) {
      return;
    }
    const rect = image.getBoundingClientRect();
    const xCoord = ((event.clientX - rect.left) / rect.width) * imageMeta.width;
    const yCoord = ((event.clientY - rect.top) / rect.height) * imageMeta.height;
    setPendingNode({ x_coord: xCoord, y_coord: yCoord });
    setNodeForm({ name: "", type: "junction" });
    setStatusMessage(
      `Captured point at (${formatCoordinate(xCoord)}, ${formatCoordinate(yCoord)}).`
    );
  }

  function toggleNodeSelection(nodeId) {
    setSelectedNodeIds((current) => {
      if (current.includes(nodeId)) {
        return current.filter((id) => id !== nodeId);
      }
      if (current.length === 2) {
        return [current[1], nodeId];
      }
      return [...current, nodeId];
    });
  }

  async function submitNode(event) {
    event.preventDefault();
    if (!pendingNode) {
      return;
    }

    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl("/nodes"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...nodeForm,
          ...pendingNode
        })
      });
      const created = await parseJsonResponse(response);
      setPendingNode(null);
      setNodeForm({ name: "", type: "junction" });
      await refreshGraph(`Created node ${created.name}.`);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function submitEdge(event) {
    event.preventDefault();
    if (selectedNodeIds.length !== 2) {
      setErrorMessage("Select two nodes to create an edge.");
      return;
    }

    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl("/edges"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_node_id: selectedNodeIds[0],
          to_node_id: selectedNodeIds[1],
          length_m: Number(edgeForm.length_m),
          resistance_per_m: Number(edgeForm.resistance_per_m),
          cable_type: edgeForm.cable_type
        })
      });
      await parseJsonResponse(response);
      setSelectedNodeIds([]);
      setEdgeForm(EMPTY_EDGE_FORM);
      await refreshGraph("Created cable edge.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function deleteNode(nodeId) {
    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl(`/nodes/${nodeId}`), {
        method: "DELETE"
      });
      if (!response.ok) {
        await parseJsonResponse(response);
      }
      setSelectedNodeIds((current) => current.filter((id) => id !== nodeId));
      await refreshGraph("Deleted node.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function deleteEdge(edgeId) {
    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl(`/edges/${edgeId}`), {
        method: "DELETE"
      });
      if (!response.ok) {
        await parseJsonResponse(response);
      }
      await refreshGraph("Deleted edge.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function uploadLayoutImage(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl("/layout-image"), {
        method: "POST",
        body: formData
      });
      const payload = await parseJsonResponse(response);
      setLayoutImageUrl(getAssetUrl(payload.layout_image_url));
      setPendingNode(null);
      await refreshGraph("Uploaded layout image.");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      event.target.value = "";
    }
  }

  async function runNearestLookup(event) {
    event.preventDefault();
    if (!nearestForm.source_node_id) {
      setErrorMessage("Choose a source node for the nearest-position lookup.");
      return;
    }

    try {
      setErrorMessage("");
      const response = await fetch(
        getApiUrl(
          `/graph/nearest?source_node_id=${encodeURIComponent(
            nearestForm.source_node_id
          )}&distance_m=${encodeURIComponent(nearestForm.distance_m)}`
        )
      );
      const payload = await parseJsonResponse(response);
      setNearestResult(payload);
      setStatusMessage("Nearest-position query completed.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function exportGraph() {
    try {
      setErrorMessage("");
      const response = await fetch(getApiUrl("/graph/export"));
      const payload = await parseJsonResponse(response);
      setExportPayload(JSON.stringify(payload, null, 2));
      setStatusMessage("Exported graph JSON.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function importGraph(event) {
    event.preventDefault();
    try {
      setErrorMessage("");
      const parsed = JSON.parse(importPayload);
      const response = await fetch(getApiUrl("/graph/import"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed)
      });
      await parseJsonResponse(response);
      await refreshGraph("Imported graph JSON.");
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  return (
    <div className="page-stack module2-page">
      <section className="hero">
        <p className="eyebrow">Module 2</p>
        <h2>Cable Layout Digitization and Graph Engine</h2>
        <p>
          Upload the NEC layout chart, click to place graph nodes, connect
          nodes with cable edges, and validate the resulting network before
          Module 3 consumes it.
        </p>
        <div className="status-row">
          <span className="status-pill">Graph Engine</span>
          <span>{statusMessage}</span>
        </div>
        {errorMessage ? <p className="error-banner">{errorMessage}</p> : null}
      </section>

      <div className="module2-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Layout Chart</p>
              <h2>Digitization Canvas</h2>
            </div>
            <label className="file-button">
              Upload Image
              <input type="file" accept="image/*" onChange={uploadLayoutImage} />
            </label>
          </div>
          <p className="panel-copy">
            Click on the layout image to capture exact image coordinates for a
            new node. Click existing node markers to select two endpoints for a
            cable edge.
          </p>

          {layoutImageUrl ? (
            <div className="layout-canvas" onClick={handleCanvasClick}>
              <img
                src={layoutImageUrl}
                alt="Cable layout"
                onLoad={handleImageLoad}
              />
              <svg
                className="graph-overlay"
                viewBox={`0 0 ${imageMeta.width} ${imageMeta.height}`}
                preserveAspectRatio="none"
              >
                {graph.edges.map((edge) => {
                  const fromNode = nodeMap[edge.from_node_id];
                  const toNode = nodeMap[edge.to_node_id];
                  if (!fromNode || !toNode) {
                    return null;
                  }
                  return (
                    <g key={edge.id}>
                      <line
                        x1={fromNode.x_coord}
                        y1={fromNode.y_coord}
                        x2={toNode.x_coord}
                        y2={toNode.y_coord}
                        className="edge-line"
                      />
                      <text
                        x={(fromNode.x_coord + toNode.x_coord) / 2}
                        y={(fromNode.y_coord + toNode.y_coord) / 2 - 8}
                        className="edge-label"
                      >
                        {edge.length_m}m
                      </text>
                    </g>
                  );
                })}

                {graph.nodes.map((node) => (
                  <g
                    key={node.id}
                    onClick={(event) => {
                      event.stopPropagation();
                      toggleNodeSelection(node.id);
                    }}
                    className="node-group"
                  >
                    <circle
                      cx={node.x_coord}
                      cy={node.y_coord}
                      r="12"
                      className={
                        selectedNodeIds.includes(node.id)
                          ? "node-marker selected"
                          : "node-marker"
                      }
                    />
                    <text
                      x={node.x_coord}
                      y={node.y_coord - 18}
                      textAnchor="middle"
                      className="node-label"
                    >
                      {node.name}
                    </text>
                  </g>
                ))}

                {pendingNode ? (
                  <circle
                    cx={pendingNode.x_coord}
                    cy={pendingNode.y_coord}
                    r="10"
                    className="node-marker pending"
                  />
                ) : null}
              </svg>
            </div>
          ) : (
            <div className="empty-layout">
              <p>No layout image uploaded yet.</p>
              <p>Upload the NEC chart to start placing nodes.</p>
            </div>
          )}
        </section>

        <div className="module2-sidebar">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Node Placement</p>
                <h2>Create Node</h2>
              </div>
              {pendingNode ? <span className="status-pill">Point Ready</span> : null}
            </div>
            <p className="panel-copy">
              {pendingNode
                ? `Pending point: (${formatCoordinate(pendingNode.x_coord)}, ${formatCoordinate(
                    pendingNode.y_coord
                  )})`
                : "Click the image to capture coordinates for a new panel, building, or junction."}
            </p>
            <form className="stack-form" onSubmit={submitNode}>
              <label>
                Node Name
                <input
                  value={nodeForm.name}
                  onChange={(event) =>
                    setNodeForm((current) => ({
                      ...current,
                      name: event.target.value
                    }))
                  }
                  placeholder="Junction 1"
                />
              </label>
              <label>
                Node Type
                <select
                  value={nodeForm.type}
                  onChange={(event) =>
                    setNodeForm((current) => ({
                      ...current,
                      type: event.target.value
                    }))
                  }
                >
                  <option value="panel">panel</option>
                  <option value="building">building</option>
                  <option value="junction">junction</option>
                </select>
              </label>
              <div className="form-actions">
                <button type="submit" disabled={!pendingNode}>
                  Create Node
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setPendingNode(null)}
                >
                  Clear Point
                </button>
              </div>
            </form>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Edge Creation</p>
                <h2>Connect Nodes</h2>
              </div>
              <span className="status-pill">{selectedNodeIds.length}/2 selected</span>
            </div>
            <p className="panel-copy">
              {selectedNodeIds.length
                ? selectedNodeIds
                    .map((nodeId) => nodeMap[nodeId]?.name || nodeId)
                    .join(" -> ")
                : "Select two node markers on the layout to create an edge."}
            </p>
            <form className="stack-form" onSubmit={submitEdge}>
              <label>
                Length (m)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={edgeForm.length_m}
                  onChange={(event) =>
                    setEdgeForm((current) => ({
                      ...current,
                      length_m: event.target.value
                    }))
                  }
                />
              </label>
              <label>
                Resistance per meter
                <input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={edgeForm.resistance_per_m}
                  onChange={(event) =>
                    setEdgeForm((current) => ({
                      ...current,
                      resistance_per_m: event.target.value
                    }))
                  }
                />
              </label>
              <label>
                Cable Type
                <input
                  value={edgeForm.cable_type}
                  onChange={(event) =>
                    setEdgeForm((current) => ({
                      ...current,
                      cable_type: event.target.value
                    }))
                  }
                />
              </label>
              <div className="form-actions">
                <button type="submit">Create Edge</button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setSelectedNodeIds([])}
                >
                  Clear Selection
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>

      <div className="module2-grid lower-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Graph Status</p>
              <h2>Validation and Traversal</h2>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => refreshGraph("Graph refreshed.")}
            >
              Refresh Graph
            </button>
          </div>
          <div className="item-grid compact-grid">
            <article className="item-card">
              <h3>Valid Layout</h3>
              <p>{validation?.valid ? "Yes" : "No"}</p>
            </article>
            <article className="item-card">
              <h3>Orphan Nodes</h3>
              <p>{validation?.orphan_nodes?.length || 0}</p>
            </article>
            <article className="item-card">
              <h3>Components</h3>
              <p>{validation?.components?.length || 0}</p>
            </article>
          </div>
          <div className="validation-grid">
            <article className="mini-panel">
              <h3>Orphan Node IDs</h3>
              <p>
                {validation?.orphan_nodes?.length
                  ? validation.orphan_nodes.join(", ")
                  : "None"}
              </p>
            </article>
            <article className="mini-panel">
              <h3>Connected Components</h3>
              <p>
                {validation?.components?.length
                  ? validation.components.map((component) => component.join(" -> ")).join(" | ")
                  : "No nodes yet"}
              </p>
            </article>
          </div>

          <form className="stack-form" onSubmit={runNearestLookup}>
            <p className="eyebrow">Nearest Position Lookup</p>
            <label>
              Source Node
              <select
                value={nearestForm.source_node_id}
                onChange={(event) =>
                  setNearestForm((current) => ({
                    ...current,
                    source_node_id: event.target.value
                  }))
                }
              >
                <option value="">Select a source node</option>
                {graph.nodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Distance (m)
              <input
                type="number"
                min="0"
                step="0.1"
                value={nearestForm.distance_m}
                onChange={(event) =>
                  setNearestForm((current) => ({
                    ...current,
                    distance_m: event.target.value
                  }))
                }
              />
            </label>
            <button type="submit">Run Lookup</button>
          </form>

          {nearestResult ? (
            <div className="mini-panel">
              <h3>Lookup Result</h3>
              <p>
                nearest_node_id: {nearestResult.nearest_node_id || "null"} | edge_id:{" "}
                {nearestResult.edge_id || "null"} | distance_along_edge_m:{" "}
                {nearestResult.distance_along_edge_m}
              </p>
            </div>
          ) : null}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Graph Data</p>
              <h2>Export and Import</h2>
            </div>
            <button type="button" onClick={exportGraph}>
              Export JSON
            </button>
          </div>
          <div className="stack-form">
            <label>
              Export Payload
              <textarea
                rows="10"
                value={exportPayload}
                onChange={(event) => setExportPayload(event.target.value)}
                placeholder="Exported graph JSON will appear here."
              />
            </label>
          </div>
          <form className="stack-form" onSubmit={importGraph}>
            <label>
              Import Payload
              <textarea
                rows="10"
                value={importPayload}
                onChange={(event) => setImportPayload(event.target.value)}
                placeholder='Paste {"version":1,"nodes":[],"edges":[]}'
              />
            </label>
            <button type="submit">Import JSON</button>
          </form>
        </section>
      </div>

      <div className="module2-grid lower-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Nodes</p>
              <h2>Node Registry</h2>
            </div>
            <span className="status-pill">{graph.nodes.length} nodes</span>
          </div>
          <div className="record-list">
            {graph.nodes.map((node) => (
              <article key={node.id} className="record-card">
                <div>
                  <h3>{node.name}</h3>
                  <p>
                    {node.type} | ({formatCoordinate(node.x_coord)},{" "}
                    {formatCoordinate(node.y_coord)})
                  </p>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => deleteNode(node.id)}
                >
                  Delete
                </button>
              </article>
            ))}
            {!graph.nodes.length ? <p>No nodes added yet.</p> : null}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Edges</p>
              <h2>Cable Registry</h2>
            </div>
            <span className="status-pill">{graph.edges.length} edges</span>
          </div>
          <div className="record-list">
            {graph.edges.map((edge) => (
              <article key={edge.id} className="record-card">
                <div>
                  <h3>{edge.cable_type}</h3>
                  <p>
                    {nodeMap[edge.from_node_id]?.name || edge.from_node_id} {" -> "}
                    {nodeMap[edge.to_node_id]?.name || edge.to_node_id} {" | "} {edge.length_m}m {" | "}
                    {edge.resistance_per_m} ohm/m
                  </p>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => deleteEdge(edge.id)}
                >
                  Delete
                </button>
              </article>
            ))}
            {!graph.edges.length ? <p>No edges added yet.</p> : null}
          </div>
        </section>
      </div>
    </div>
  );
}
