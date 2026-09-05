import { useRef, useState } from "react";

// WAI-ARIA tabs pattern: role="tablist"/"tab"/"tabpanel", aria-selected,
// aria-controls/labelledby pairing, and roving tabindex with Left/Right/
// Home/End arrow-key navigation (only the active tab is in the Tab order —
// arrow keys move selection between tabs, matching how every native tab
// widget behaves).
export default function Tabs({ tabs, onActiveChange }) {
  const [active, setActive] = useState(0);
  const tabRefs = useRef([]);

  function select(idx) {
    setActive(idx);
    onActiveChange?.(tabs[idx].label);
  }

  function onKeyDown(e) {
    const last = tabs.length - 1;
    let next = null;
    if (e.key === "ArrowRight") next = active === last ? 0 : active + 1;
    else if (e.key === "ArrowLeft") next = active === 0 ? last : active - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    if (next === null) return;
    e.preventDefault();
    select(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <div>
      <div className="tab-bar" role="tablist" aria-label="Dashboard sections" onKeyDown={onKeyDown}>
        {tabs.map((tab, idx) => (
          <button
            key={tab.label}
            ref={(el) => (tabRefs.current[idx] = el)}
            id={`tab-${idx}`}
            role="tab"
            aria-selected={idx === active}
            aria-controls={`tabpanel-${idx}`}
            tabIndex={idx === active ? 0 : -1}
            className={`tab-button${idx === active ? " tab-button--active" : ""}`}
            onClick={() => select(idx)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        id={`tabpanel-${active}`}
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
        tabIndex={0}
      >
        {tabs[active].content}
      </div>
    </div>
  );
}
