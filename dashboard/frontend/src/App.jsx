import { useState } from "react";
import Tabs from "./components/Tabs";
import Overview from "./tabs/Overview";
import LiveIncidents from "./tabs/LiveIncidents";
import HistoricalArchive from "./tabs/HistoricalArchive";
import EvaluationTrials from "./tabs/EvaluationTrials";
import FireStation from "./tabs/FireStation";
import LiveView from "./tabs/LiveView";
import { fetchIncidents, fetchS3Archive, fetchTrials, fetchFireStation, fetchLiveSensors } from "./api";
import { usePolling } from "./usePolling";
import { useWebSocket } from "./useWebSocket";

// Poll cadences per the developer's brief: incidents change fastest (every
// alert), S3 far less often, trials/fire-station rarely — those two poll on
// tab focus rather than a tight interval. live-sensors is new (Phase 11
// design pass) and polls fast since it's a live 1 Hz feed — active only
// while Overview is focused, no reason to poll it in the background.
const INCIDENTS_INTERVAL_MS = 5000;
const S3_INTERVAL_MS = 30000;
const LOW_CHURN_INTERVAL_MS = 60000;
const LIVE_SENSORS_INTERVAL_MS = 3000;

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
  const { data: station, error: stationError, loading: stationLoading } = usePolling(
    fetchFireStation,
    LOW_CHURN_INTERVAL_MS,
    activeTabLabel === "Nearest Fire Station" || activeTabLabel === "Overview"
  );
  const { data: liveSensors } = usePolling(
    fetchLiveSensors,
    LIVE_SENSORS_INTERVAL_MS,
    activeTabLabel === "Overview"
  );
  // Stage 5: Live View gets a 1 Hz WebSocket push instead of polling.
  // Identical payload and identical { data, error, loading } contract as
  // the polling hook above, so swapping back is a one-line change if the
  // socket ever misbehaves. Active only while the tab is focused — no
  // reason to hold a socket open for a tab nobody is looking at.
  const {
    data: liveView,
    error: liveViewError,
    loading: liveViewLoading,
  } = useWebSocket("/ws/live", activeTabLabel === "Live View");

  const incidentList = incidents ?? [];

  const tabs = [
    {
      label: "Overview",
      content: (
        <Overview
          incidents={incidentList}
          liveSensors={liveSensors}
          station={station}
          loading={incidentsLoading}
        />
      ),
    },
    {
      label: "Live View",
      content: (
        <LiveView
          liveSensors={liveView}
          error={liveViewError}
          loading={liveViewLoading}
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
    {
      label: "Nearest Fire Station",
      content: <FireStation station={station} error={stationError} loading={stationLoading} />,
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
