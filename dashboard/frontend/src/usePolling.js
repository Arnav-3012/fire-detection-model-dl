import { useEffect, useRef, useState } from "react";

// Shared polling hook for every tab's data source. `active` lets a tab pause
// its own poll while not focused (used by the low-churn trials/fire-station
// endpoints per the developer's brief: poll those on focus, not constantly).
export function usePolling(fetchFn, intervalMs, active = true) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetchFnRef = useRef(fetchFn);
  fetchFnRef.current = fetchFn;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    async function run() {
      try {
        const result = await fetchFnRef.current();
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run();
    const id = setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs, active]);

  return { data, error, loading };
}
