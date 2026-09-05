import { useMemo, useState } from "react";
import LevelBadge from "../components/LevelBadge";
import StateCard from "../components/StateCard";
import Reveal from "../components/Reveal";
import { SkeletonPanel } from "../components/Skeleton";
import { ArchiveIcon } from "../components/icons";

function OwnerResponsePill({ response }) {
  if (!response) return <span className="status-pill status-pill--neutral">none</span>;
  const isCancelled = /cancel/i.test(response);
  return (
    <span className={`status-pill status-pill--${isCancelled ? "positive" : "negative"}`}>
      {response}
    </span>
  );
}

export default function HistoricalArchive({ archive, error, loading }) {
  const devices = archive?.devices ?? {};
  const deviceNames = useMemo(() => Object.keys(devices), [devices]);
  const [deviceFilter, setDeviceFilter] = useState("ALL");

  if (loading) {
    return (
      <div className="tab-content">
        <SkeletonPanel height={220} />
      </div>
    );
  }

  if (error || archive?.ok === false) {
    return (
      <div className="tab-content">
        <div className="state-card-wrap">
          <StateCard kind="error">
            Could not load the S3 archive{archive?.error ? `: ${archive.error}` : ""}. Check AWS
            credentials and config.yaml's aws.s3_bucket.
          </StateCard>
        </div>
      </div>
    );
  }

  const visibleDevices = deviceFilter === "ALL" ? deviceNames : [deviceFilter];
  const isEmpty = deviceNames.length === 0;

  return (
    <div className="tab-content">
      <div className="filters">
        <select value={deviceFilter} onChange={(e) => setDeviceFilter(e.target.value)}>
          <option value="ALL">All devices</option>
          {deviceNames.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      {isEmpty ? (
        <div className="state-card-wrap">
          <StateCard kind="empty">No archived incidents in S3 yet.</StateCard>
        </div>
      ) : (
        visibleDevices.map((device) => (
          <Reveal className="panel glass" key={device}>
            <h3 className="panel-title"><ArchiveIcon />{device}</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Level</th>
                  <th>Reason</th>
                  <th>Owner response</th>
                  <th>S3 key</th>
                </tr>
              </thead>
              <tbody>
                {devices[device].map((inc) => (
                  <tr key={inc._s3_key}>
                    <td>{inc.timestamp}</td>
                    <td>
                      <LevelBadge level={inc.level} />
                    </td>
                    <td>{inc.reason}</td>
                    <td>
                      <OwnerResponsePill response={inc.owner_response} />
                    </td>
                    <td className="mono-cell">{inc._s3_key}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Reveal>
        ))
      )}
    </div>
  );
}
