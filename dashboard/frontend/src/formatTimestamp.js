// Human-readable timestamp formatting, matching the convention already
// established weeks ago in agent/compose.py's natural_time_phrase() for
// Telegram/SMS alert text (e.g. "at 9:29 PM on Sep 3") — never a raw ISO
// string on any surface a person reads. This is the dashboard-side mirror
// of that same convention, applied to every raw-timestamp display here.
//
// Accepts an ISO 8601 string (edge/main.py's incident timestamps,
// eval/results.csv's trial timestamps) or a unix-seconds number
// (edge/livelog.py's live-sensor samples). Returns the input unchanged if
// it can't be parsed, rather than showing "Invalid Date".
export function formatTimestamp(value) {
  if (value == null || value === "") return value;
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const time = date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  const day = date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  return `${time}, ${day}`;
}
