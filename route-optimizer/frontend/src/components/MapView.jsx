import React, { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvents } from "react-leaflet";
import L from "leaflet";

// Build a numbered "shipping label" style div-icon rather than the default
// Leaflet pin — this doubles as the stop-sequence indicator on the map.
function numberedIcon({ number, isDepot, visited }) {
  const bg = isDepot ? "var(--amber)" : "var(--panel-raised)";
  const border = isDepot ? "var(--amber)" : visited ? "var(--accent)" : "var(--border)";
  const color = isDepot ? "#0a0e13" : "var(--text)";
  const label = isDepot ? "D" : number;
  return L.divIcon({
    className: "",
    html: `<div style="
        width:30px;height:30px;border-radius:50% 50% 50% 0;
        transform:rotate(-45deg);
        background:${bg};border:2px solid ${border};
        display:flex;align-items:center;justify-content:center;
        box-shadow:0 2px 6px rgba(0,0,0,0.5);
      ">
        <span style="
          transform:rotate(45deg);
          font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:12px;color:${color};
        ">${label}</span>
      </div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -28],
  });
}

function ClickToAddStop({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick(e.latlng);
    },
  });
  return null;
}

export default function MapView({
  depot,
  stops,
  optimizedOrder, // array of stop ids in optimized order, or null
  routeGeometry,  // array of {lat,lng} or null
  onDepotMove,
  onStopMove,
  onMapClick,
  addStopMode,
}) {
  const center = useMemo(() => {
    if (depot) return [depot.location.lat, depot.location.lng];
    if (stops.length) return [stops[0].location.lat, stops[0].location.lng];
    return [51.5074, -0.1278]; // London, sensible default
  }, [depot, stops]);

  const polylinePositions = useMemo(() => {
    if (routeGeometry && routeGeometry.length) {
      return routeGeometry.map((p) => [p.lat, p.lng]);
    }
    return null;
  }, [routeGeometry]);

  const sequenceLookup = useMemo(() => {
    if (!optimizedOrder) return null;
    const map = {};
    optimizedOrder.forEach((id, idx) => {
      map[id] = idx;
    });
    return map;
  }, [optimizedOrder]);

  return (
    <MapContainer
      center={center}
      zoom={13}
      style={{ height: "100%", width: "100%", background: "#0a0e13" }}
      zoomControl={true}
    >
      {/* Standard OSM tile layer — free, no API key required */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <ClickToAddStop onMapClick={onMapClick} />

      {depot && (
        <Marker
          position={[depot.location.lat, depot.location.lng]}
          icon={numberedIcon({ isDepot: true })}
          draggable
          eventHandlers={{
            dragend: (e) => onDepotMove(e.target.getLatLng()),
          }}
        >
          <Popup>
            <strong>Depot</strong>
            <br />
            {depot.label || "Starting location"}
          </Popup>
        </Marker>
      )}

      {stops.map((stop) => {
        const displayNumber = sequenceLookup ? sequenceLookup[stop.id] : stops.indexOf(stop) + 1;
        return (
          <Marker
            key={stop.id}
            position={[stop.location.lat, stop.location.lng]}
            icon={numberedIcon({ number: displayNumber, visited: !!sequenceLookup })}
            draggable
            eventHandlers={{
              dragend: (e) => onStopMove(stop.id, e.target.getLatLng()),
            }}
          >
            <Popup>
              <strong>Stop {displayNumber}</strong>
              <br />
              {stop.label || `${stop.location.lat.toFixed(5)}, ${stop.location.lng.toFixed(5)}`}
            </Popup>
          </Marker>
        );
      })}

      {polylinePositions && (
        <Polyline
          positions={polylinePositions}
          pathOptions={{ color: "#33d17a", weight: 4, opacity: 0.9 }}
        />
      )}

      {addStopMode && (
        <div className="map-hint">Click the map to drop a delivery stop</div>
      )}
    </MapContainer>
  );
}
