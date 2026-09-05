import { useEffect, useRef, useState } from "react";

// Animates a numeric metric-card value from its previous value to the next
// over ~350ms whenever it changes (design brief: "number count-up animation
// on metric cards"). Non-numeric values (percent strings, "—", etc.) render
// as-is, no animation attempted.
export default function CountUp({ value }) {
  const numeric = typeof value === "number" || (typeof value === "string" && /^-?\d+$/.test(value));
  const target = numeric ? Number(value) : null;
  const [display, setDisplay] = useState(target ?? value);
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
      const current = Math.round(from + (to - from) * eased);
      setDisplay(current);
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
