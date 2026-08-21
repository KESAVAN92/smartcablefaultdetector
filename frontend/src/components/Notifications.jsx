import React, { useEffect, useState, useContext } from "react";
import { AuthContext } from "../auth";

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = 880;
    o.connect(g);
    g.connect(ctx.destination);
    o.start();
    g.gain.setValueAtTime(0.1, ctx.currentTime);
    setTimeout(() => {
      o.stop();
      ctx.close();
    }, 200);
  } catch (e) {
    // ignore
  }
}

export default function Notifications() {
  const { token } = useContext(AuthContext);
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (!token) return;
    let wsProto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${wsProto}://${window.location.host}/alerts/stream`;
    const ws = new WebSocket(url);
    ws.onopen = () => {
      console.debug("alerts ws open");
      // send a ping to register if needed
      ws.send("hello");
    };
    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        setItems((s) => [payload, ...s].slice(0, 8));
        beep();
      } catch (e) {
        console.error(e);
      }
    };
    ws.onclose = () => console.debug("alerts ws closed");
    return () => ws.close();
  }, [token]);

  return (
    <div className="notifications-root">
      {items.map((it) => (
        <div key={it.event_id} className="toast">
          <strong>{it.type}</strong>: {it.message}
          <div className="time">{it.created_at}</div>
        </div>
      ))}
    </div>
  );
}
