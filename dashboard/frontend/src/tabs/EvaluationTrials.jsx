import Plot from "react-plotly.js";
import { darkLayout, plotlyConfig } from "../plotlyTheme";
import StateCard from "../components/StateCard";
import Reveal from "../components/Reveal";
import { SkeletonPanel } from "../components/Skeleton";
import { ChartIcon, CheckListIcon } from "../components/icons";

export default function EvaluationTrials({ trials, loading }) {
  if (loading) {
    return (
      <div className="tab-content">
        <SkeletonPanel height={200} />
        <SkeletonPanel height={200} />
      </div>
    );
  }

  if (!trials || trials.ok === false) {
    return (
      <div className="tab-content">
        <div className="state-card-wrap">
          <StateCard kind="empty">
            No trial data yet — evaluation trials (info.md 4.4, Phase 11) haven't been run.
          </StateCard>
        </div>
      </div>
    );
  }

  const rows = trials.rows;
  const outcomeCounts = {};
  for (const row of rows) {
    const key = row.actual_outcome ?? "unknown";
    outcomeCounts[key] = (outcomeCounts[key] ?? 0) + 1;
  }

  return (
    <div className="tab-content">
      <Reveal className="panel glass">
        <h3 className="panel-title"><ChartIcon />Outcome distribution</h3>
        <Plot
          data={[
            {
              x: Object.keys(outcomeCounts),
              y: Object.values(outcomeCounts),
              type: "bar",
              marker: { color: "#f59e0b" },
            },
          ]}
          layout={{ ...darkLayout, height: 300 }}
          config={plotlyConfig}
          useResizeHandler
          style={{ width: "100%" }}
        />
      </Reveal>

      <Reveal className="panel glass" delay={80}>
        <h3 className="panel-title"><CheckListIcon />Trials</h3>
        <table className="data-table">
          <thead>
            <tr>
              {Object.keys(rows[0] ?? {}).map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx}>
                {Object.values(row).map((val, i) => (
                  <td key={i}>{val}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Reveal>
    </div>
  );
}
