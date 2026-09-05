import StateCard from "../components/StateCard";
import { SkeletonPanel } from "../components/Skeleton";
import { PinIcon, BellRingIcon } from "../components/icons";

export default function FireStation({ station, error, loading }) {
  if (loading) {
    return (
      <div className="tab-content">
        <div className="grid-12">
          <div className="col-8">
            <SkeletonPanel height={140} />
          </div>
          <div className="col-4">
            <SkeletonPanel height={140} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      <div className="grid-12">
        <div className="col-8">
          <div className="panel glass glass--cool station-panel" style={{ height: "100%" }}>
            <h3 className="panel-title"><PinIcon />Nearest fire station</h3>
            {error ? (
              <div className="state-card-wrap">
                <StateCard kind="error">Could not load fire station data: {error}</StateCard>
              </div>
            ) : !station ? (
              <div className="state-card-wrap">
                <StateCard kind="empty">Looking up the nearest station…</StateCard>
              </div>
            ) : station.found ? (
              <div className="station-info station-info--fill">
                <div>
                  <span className="metric-label">Name</span>
                  <div className="metric-value metric-value--lg">{station.name}</div>
                </div>
                <div>
                  <span className="metric-label">Distance</span>
                  <div className="metric-value metric-value--lg">{station.distance_km} km</div>
                </div>
                <div>
                  <span className="metric-label">Phone</span>
                  <div className="metric-value metric-value--lg">{station.phone ?? "Not listed on OSM"}</div>
                </div>
              </div>
            ) : (
              <div className="state-card-wrap">
                <StateCard kind="empty">{station.line}</StateCard>
              </div>
            )}
          </div>
        </div>
        <div className="col-4">
          <div className="panel glass" style={{ height: "100%" }}>
            <h3 className="panel-title"><BellRingIcon />Emergency numbers</h3>
            <p className="metric-sub" style={{ marginBottom: 16 }}>Display-only — never auto-dialed.</p>
            <div className="station-info" style={{ flexDirection: "column", gap: 18 }}>
              <div>
                <span className="metric-label">Fire</span>
                <div className="metric-value">{station?.fire_number ?? "101"}</div>
              </div>
              <div>
                <span className="metric-label">Unified emergency</span>
                <div className="metric-value">{station?.unified_number ?? "112"}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
