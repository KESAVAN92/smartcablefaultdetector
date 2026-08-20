/**
 * useGraphData — fetches graph nodes + edges from Module 3's /graph endpoint.
 * TODO-integrate: when M2 is live, this can switch to /api/module2/graph directly.
 */

import { useCallback, useEffect, useState } from "react";

const API = import.meta.env.VITE_BACKEND_URL
  ? `${import.meta.env.VITE_BACKEND_URL}/api/module3`
  : "/api/module3";

export function useGraphData() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchGraph = useCallback(() => {
    setLoading(true);
    fetch(`${API}/graph`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setGraphData(data);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { graphData, loading, error, refetch: fetchGraph };
}
