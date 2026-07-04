import React from "react";

function formatDuration(seconds) {
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function DeliveryList({ orderedStops }) {
  if (!orderedStops || orderedStops.length === 0) return null;

  return (
    <div className="delivery-list">
      <div className="section-label">Optimized order</div>
      <ol>
        {orderedStops.map((entry) => (
          <li key={entry.stop.id} className="delivery-item">
            <div className="delivery-item-index">{entry.sequence_index + 1}</div>
            <div className="delivery-item-body">
              <div className="delivery-item-label truncate">
                {entry.stop.label ||
                  `${entry.stop.location.lat.toFixed(4)}, ${entry.stop.location.lng.toFixed(4)}`}
              </div>
              <div className="delivery-item-meta mono">
                +{formatDuration(entry.leg_duration_s)} leg · {(entry.leg_distance_m / 1000).toFixed(1)} km
                {entry.estimated_arrival && (
                  <> · ETA {new Date(entry.estimated_arrival).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
