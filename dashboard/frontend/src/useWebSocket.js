import { useEffect, useRef, useState } from "react";
import { WS_BASE } from "./api";

// Stage 5 (2026-09-23): live data over a WebSocket instead of polling.
//
// Returns the EXACT same { data, error, loading } shape as usePolling, and
// the server pushes the exact same payload as GET /api/live-sensors. That
// symmetry is deliberate: any component written against usePolling works
// here unchanged, and falling back to polling is a one-line swap at the
// call site if the socket ever proves troublesome.
//
// Auto-reconnects with backoff. A dashboard left open overnight will see
// the backend restart, a laptop sleep, a WiFi drop — none of which should
// require a manual page refresh.

const INITIAL_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 15000;

export function useWebSocket(path, active = true) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const socketRef = useRef(null);
  const timerRef = useRef(null);
  const delayRef = useRef(INITIAL_RECONNECT_MS);
  // Guards against a socket that closes AFTER the effect has torn down
  // (tab switch, unmount) scheduling a reconnect nobody wants.
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!active) return;
    cancelledRef.current = false;

    function connect() {
      if (cancelledRef.current) return;
      // Derived from api.js's BASE, NOT window.location: this app talks to
      // a backend on a different port (8001) than the Vite dev server
      // (5173), so a same-origin URL would connect to the dev server and
      // never reach the API.
      const url = `${WS_BASE}${path}`;

      let socket;
      try {
        socket = new WebSocket(url);
      } catch (err) {
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        // Reset backoff only on a SUCCESSFUL open, so a flapping server
        // doesn't get hammered at the initial interval forever.
        delayRef.current = INITIAL_RECONNECT_MS;
        setError(null);
      };

      socket.onmessage = (event) => {
        try {
          setData(JSON.parse(event.data));
          setError(null);
        } catch (err) {
          // One malformed frame must not kill the feed — the next one is
          // a second away.
          setError("malformed live payload");
        } finally {
          setLoading(false);
        }
      };

      socket.onerror = () => {
        // onerror is always followed by onclose, which handles the
        // reconnect. Recording the message here would just race it.
        setError("live connection error");
      };

      socket.onclose = () => {
        socketRef.current = null;
        setLoading(false);
        scheduleReconnect();
      };
    }

    function scheduleReconnect() {
      if (cancelledRef.current) return;
      const delay = delayRef.current;
      delayRef.current = Math.min(delay * 2, MAX_RECONNECT_MS);
      timerRef.current = setTimeout(connect, delay);
    }

    connect();

    return () => {
      cancelledRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      if (socketRef.current) {
        // Clear onclose first: otherwise our own teardown triggers the
        // reconnect path.
        socketRef.current.onclose = null;
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [path, active]);

  return { data, error, loading };
}
