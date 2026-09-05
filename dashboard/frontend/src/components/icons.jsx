// Hand-written inline SVG icons — no icon-library dependency added.
// Shared stroke conventions (currentColor, 1.6 width, round caps/joins) so
// every icon sits at the same visual weight regardless of which card it's
// used in. Each is purely decorative next to a text label, so they carry
// aria-hidden rather than their own accessible name.

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": "true",
  focusable: "false",
};

export function FlameIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 2.5c1.2 2.1-.3 3.4-1.3 4.6-1.4 1.7-2.3 3.3-2.3 5.2a3.6 3.6 0 0 0 3.6 3.6c.4 0 .8-.05 1.1-.15-.7-.9-.9-1.7-.6-2.6.3-.9 1-1.5 1.4-2.3.6 1 1.6 1.8 1.6 3.4a3.9 3.9 0 0 1-3.9 3.9 5.1 5.1 0 0 1-5.1-5.1c0-3.6 2.6-5.6 3.9-7.3.9-1.1 1.5-2.1 1.6-3.3Z" />
    </svg>
  );
}

export function PinIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 21s-6.5-5.9-6.5-11A6.5 6.5 0 0 1 18.5 10c0 5.1-6.5 11-6.5 11Z" />
      <circle cx="12" cy="10" r="2.3" />
    </svg>
  );
}

export function ClockIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

export function ChartIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 19V6" />
      <path d="M4 19h16" />
      <path d="M8 19v-6" />
      <path d="M12.5 19V9" />
      <path d="M17 19v-9.5" />
    </svg>
  );
}

export function GaugeIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 15a8 8 0 1 1 16 0" />
      <path d="M12 15 15.2 9.8" />
      <path d="M12 15.8a.8.8 0 1 0 0-1.6.8.8 0 0 0 0 1.6Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function AlertTriangleIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 9v4" />
      <path d="M10.29 3.86 1.82 18a1 1 0 0 0 .86 1.5h18.64a1 1 0 0 0 .86-1.5L13.71 3.86a1 1 0 0 0-1.72 0Z" />
      <circle cx="12" cy="16.2" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function BellRingIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M8 17.5a4 4 0 0 0 8 0" />
      <path d="M6 17.5h12l-1.6-2.4A6 6 0 0 1 15.4 12V10a3.4 3.4 0 1 0-6.8 0v2a6 6 0 0 1-1 3.1Z" />
      <path d="M4.2 6.5a9 9 0 0 1 2.4-3" />
      <path d="M19.8 6.5a9 9 0 0 0-2.4-3" />
    </svg>
  );
}

export function ArchiveIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect x="3.5" y="4" width="17" height="4.2" rx="1" />
      <path d="M4.5 8.2V19a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V8.2" />
      <path d="M10 12.5h4" />
    </svg>
  );
}

export function CheckListIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9 6h10" />
      <path d="M9 12h10" />
      <path d="M9 18h10" />
      <path d="m4 6 1 1 1.8-2" />
      <path d="m4 12 1 1 1.8-2" />
      <path d="m4 18 1 1 1.8-2" />
    </svg>
  );
}

export function PercentIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M5 19 19 5" />
      <circle cx="7.5" cy="7.5" r="2" />
      <circle cx="16.5" cy="16.5" r="2" />
    </svg>
  );
}
