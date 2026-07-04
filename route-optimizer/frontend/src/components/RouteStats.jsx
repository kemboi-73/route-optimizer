import React from "react";

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatDistance(meters) {
  return `${(meters / 1000).toFixed(1)} km`;
}

function Stat({ label, value, sub, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={accent ? "stat-value accent" : "stat-value"}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export default function RouteStats({ statistics, algorithm, solverStatus }) {
  if (!statistics) {
    return (
      <div className="stats-panel empty">
        <div className="empty-state">
          Set a depot, add stops, and hit <strong>Optimize route</strong> to see
          live route metrics here.
        </div>
      </div>
    );
  }

  const s = statistics;

  return (
    <div className="stats-panel">
      <div className="stats-grid">
        <Stat label="Total distance" value={formatDistance(s.total_distance_m)} />
        <Stat label="Total drive time" value={formatDuration(s.total_duration_s)} />
        <Stat label="Stops" value={s.num_stops} />
        <Stat label="Avg. dwell / stop" value={`${s.average_stop_service_minutes}m`} />
        <Stat
          label="Time saved vs. naive order"
          value={formatDuration(s.time_saved_s)}
          sub={`${s.time_saved_percent}% faster`}
          accent
        />
        <Stat label="Efficiency score" value={`${s.route_efficiency_score}/100`} accent />
        <Stat label="Est. fuel used" value={`${s.estimated_fuel_liters} L`} sub={`≈ ${s.estimated_fuel_cost} cost units`} />
        <Stat label="Est. CO₂" value={`${s.estimated_co2_kg} kg`} />
      </div>
      {s.estimated_completion_time && (
        <div className="completion-line">
          Estimated completion:{" "}
          <span className="mono">{new Date(s.estimated_completion_time).toLocaleString()}</span>
        </div>
      )}
      <div className="algo-line">
        {algorithm} · solver status: <span className="mono">{solverStatus}</span>
      </div>
    </div>
  );
}
