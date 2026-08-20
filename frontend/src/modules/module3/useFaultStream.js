/**
 * useFaultStream — subscribes to Module 3's /fault-events WebSocket namespace.
 * Returns { liveEvents, connected, clearEvents }
 *
 * TODO-integrate: Once M1 is live, also subscribe to /readings for raw readings overlay.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { io } from "socket.io-client";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:5000";
const MAX_LIVE_EVENTS = 50;

export function useFaultStream() {
  const [liveEvents, setLiveEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);

  useEffect(() => {
    const socket = io(`${BACKEND_URL}/fault-events`, {
      transports: ["websocket", "polling"],
      reconnectionAttempts: 10,
      reconnectionDelay: 1500,
    });
    socketRef.current = socket;

    socket.on("connect", () => {
      console.log("[useFaultStream] connected");
      setConnected(true);
    });

    socket.on("disconnect", () => {
      console.log("[useFaultStream] disconnected");
      setConnected(false);
    });

    socket.on("new_fault_event", (event) => {
      console.log("[useFaultStream] new_fault_event", event.id);
      setLiveEvents((prev) => [event, ...prev].slice(0, MAX_LIVE_EVENTS));
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const clearEvents = useCallback(() => setLiveEvents([]), []);

  return { liveEvents, connected, clearEvents };
}
