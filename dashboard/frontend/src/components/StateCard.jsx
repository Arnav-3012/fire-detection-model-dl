// Shared glass-card empty/error state — used across every tab so "no data
// yet" and "fetch failed" read as the same considered UI, not plain text
// floating on the page (design brief).
const ICONS = {
  empty: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 19V6a2 2 0 0 1 2-2h7l5 5v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 4v4a1 1 0 0 0 1 1h4" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 13h6M9 16h4" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.29 3.86 1.82 18a1 1 0 0 0 .86 1.5h18.64a1 1 0 0 0 .86-1.5L13.71 3.86a1 1 0 0 0-1.72 0Z" />
      <circle cx="12" cy="16.2" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  ),
  offline: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.5 16.5a5 5 0 0 1 6-1.2M5 12.5a10 10 0 0 1 3-2.2M19 12.5a10 10 0 0 0-2.1-1.8M12 20h.01" />
    </svg>
  ),
};

export default function StateCard({ kind = "empty", children }) {
  return (
    <div className={`glass state-card${kind === "error" ? " state-card--error" : ""}`}>
      {ICONS[kind] ?? ICONS.empty}
      <span>{children}</span>
    </div>
  );
}
