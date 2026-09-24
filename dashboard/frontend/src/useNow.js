import { useEffect, useState } from "react";

// Wall-clock that re-renders every `intervalMs`, so "updated 3s ago" and
// staleness keep ticking between WebSocket pushes — and still flip to
// "offline" when the pushes stop arriving entirely.
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
