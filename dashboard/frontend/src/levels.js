// Mirrors edge/fusion.py's Level enum exactly (SAFE=0..CRITICAL=3) so the
// dashboard's color language and edge/fusion.py's severity ordering never
// drift apart — this file is the single place that mapping lives.
export const LEVELS = ["SAFE", "WATCH", "WARNING", "CRITICAL"];

export const LEVEL_COLOR = {
  SAFE: "#2dd4a7",
  WATCH: "#e8c547",
  WARNING: "#f0954a",
  CRITICAL: "#f0453a",
};

export const levelIndex = (level) => LEVELS.indexOf(level);
