import { useState } from "react";
import Tabs from "./components/Tabs";
import Overview from "./tabs/Overview";
import LiveIncidents from "./tabs/LiveIncidents";
import HistoricalArchive from "./tabs/HistoricalArchive";
import EvaluationTrials from "./tabs/EvaluationTrials";
import { fetchIncidents, fetchS3Archive, fetchTrials, fetchFireStation } from "./api";
import { usePolling } from "./usePolling";
import { useWebSocket } from "./useWebSocket";

// Poll cadences: incidents change fastest (every alert), S3 far less
// often, trials/fire-station rarely. The live feed is not polled at all —
// it arrives over the /ws/live socket below.
const INCIDENTS_INTERVAL_MS = 5000;
const S3_INTERVAL_MS = 30000;
const LOW_CHURN_INTERVAL_MS = 60000;

export default function App() {
  const [activeTabLabel, setActiveTabLabel] = useState("Overview");

  const { data: incidents, error: incidentsError, loading: incidentsLoading } = usePolling(
    fetchIncidents,
    INCIDENTS_INTERVAL_MS
  );
  const { data: archive, error: archiveError, loading: archiveLoading } = usePolling(
    fetchS3Archive,
    S3_INTERVAL_MS,
    activeTabLabel === "Historical Archive"
  );
  const { data: trials, loading: trialsLoading } = usePolling(
    fetchTrials,
    LOW_CHURN_INTERVAL_MS,
    activeTabLabel === "Evaluation Trials"
  );
  const { data: station } = usePolling(
    fetchFireStation,
    LOW_CHURN_INTERVAL_MS,
    activeTabLabel === "Overview"
  );
  // Live feed for the home page (2026-09-24: the Live View tab folded into
  // Overview). 1 Hz server push, same payload as GET /api/live-sensors, so
  // falling back to usePolling(fetchLiveSensors, ...) is a one-line swap.
  // Held only while Overview is focused.
  const {
    data: liveSensors,
    error: liveError,
  } = useWebSocket("/ws/live", activeTabLabel === "Overview");

  const incidentList = incidents ?? [];

  const tabs = [
    {
      label: "Overview",
      content: (
        <Overview
          incidents={incidentList}
          liveSensors={liveSensors}
          liveError={liveError}
          station={station}
          loading={incidentsLoading}
        />
      ),
    },
    {
      label: "Live Incidents",
      content: <LiveIncidents incidents={incidentList} loading={incidentsLoading} />,
    },
    {
      label: "Historical Archive",
      content: <HistoricalArchive archive={archive} error={archiveError} loading={archiveLoading} />,
    },
    {
      label: "Evaluation Trials",
      content: <EvaluationTrials trials={trials} loading={trialsLoading} />,
    },
  ];

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>FireWatch</h1>
        <span className="app-subtitle">hazard monitoring dashboard</span>
        {incidentsError && <span className="header-error">incidents feed: {incidentsError}</span>}
      </header>
      <Tabs tabs={tabs} onActiveChange={setActiveTabLabel} />
    </div>
  );
}
