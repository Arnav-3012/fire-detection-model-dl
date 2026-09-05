// Overrides Plotly's stock light theme so every chart matches the dark UI
// (developer brief: "Plotly's default light theme must be overridden").
// Transparent paper/plot background so charts sit on the glass panel's own
// blur rather than painting a flat rectangle over it. Spread this into each
// chart's own `layout` object.
//
// Brand pivot (2026-09-04): gridline/zeroline color and tick font moved off
// the old cool blue-gray (#c7ccd6 text, rgba(148,163,184,...) grid) onto the
// same warm-neutral tokens the rest of the UI now uses (--text/--border),
// so charts read as part of the same ember-on-ash identity rather than a
// separate cooler-toned layer.
export const darkLayout = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#e4d9d1", family: "system-ui, sans-serif" },
  xaxis: { gridcolor: "rgba(214,180,154,0.14)", zerolinecolor: "rgba(214,180,154,0.14)" },
  yaxis: { gridcolor: "rgba(214,180,154,0.14)", zerolinecolor: "rgba(214,180,154,0.14)" },
  margin: { t: 30, r: 20, l: 50, b: 40 },
};

export const plotlyConfig = { displayModeBar: false, responsive: true };
