import { useEffect, useRef, useState } from "react";

// Animates a numeric metric-card value from its previous value to the next
// over ~350ms whenever it changes (design brief: "number count-up animation
// on metric cards"). Non-numeric values (percent strings, "—", etc.) render
// as-is, no animation attempted. `decimals` animates fractional values
// (p_fire, hazard index) at a fixed precision instead of rounding them.
export default function CountUp({ value, decimals = 0 }) {
  const numeric = typeof value === "number" || (typeof value === "string" && /^-?\d+$/.test(value));
  const fmt = (v) => (decimals ? v.toFixed(decimals) : Math.round(v));
  const target = numeric ? Number(value) : null;
  const [display, setDisplay] = useState(numeric ? fmt(target) : value);
  const fromRef = useRef(target ?? 0);
  const rafRef = useRef(null);

  useEffect(() => {
    if (!numeric) {
      setDisplay(value);
      return;
    }
    const from = fromRef.current;
    const to = target;
    if (from === to) return;
    const duration = 350;
    const start = performance.now();

    function tick(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(fmt(from + (to - from) * eased));
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, numeric]);

  return <span className="count-up">{display}</span>;
}
