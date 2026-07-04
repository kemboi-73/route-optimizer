import React, { useCallback, useState } from "react";
import MapView from "./components/MapView.jsx";
import Sidebar from "./components/Sidebar.jsx";
import RouteStats from "./components/RouteStats.jsx";
import DeliveryList from "./components/DeliveryList.jsx";
import { optimizeRoute } from "./services/api.js";
import "./styles/app.css";

let nextId = 1;
function makeId() {
  return `stop-${nextId++}`;
}

export default function App() {
  const [depot, setDepot] = useState(null);
  const [stops, setStops] = useState([]);
  const [endStrategy, setEndStrategy] = useState("return_to_depot");
  const [result, setResult] = useState(null); // OptimizeResponse
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [error, setError] = useState(null);

  const handleSetDepotFromSearch = useCallback((geoResult) => {
    setDepot({
      id: "depot",
      label: geoResult.display_name,
      location: geoResult.location,
      service_time_minutes: 0,
    });
    setResult(null);
  }, []);

  const handleAddStopFromSearch = useCallback((geoResult) => {
    setStops((prev) => [
      ...prev,
      {
        id: makeId(),
        label: geoResult.display_name,
        location: geoResult.location,
        service_time_minutes: 5,
        priority: 0,
      },
    ]);
    setResult(null);
  }, []);

  const handleMapClick = useCallback(
    (latlng) => {
      if (!depot) {
        setDepot({
          id: "depot",
          label: null,
          location: { lat: latlng.lat, lng: latlng.lng },
          service_time_minutes: 0,
        });
      } else {
        setStops((prev) => [
          ...prev,
          {
            id: makeId(),
            label: null,
            location: { lat: latlng.lat, lng: latlng.lng },
            service_time_minutes: 5,
            priority: 0,
          },
        ]);
      }
      setResult(null);
    },
    [depot]
  );

  const handleDepotMove = useCallback((latlng) => {
    setDepot((prev) => ({ ...prev, location: { lat: latlng.lat, lng: latlng.lng }, label: prev.label }));
    setResult(null);
  }, []);

  const handleStopMove = useCallback((id, latlng) => {
    setStops((prev) =>
      prev.map((s) => (s.id === id ? { ...s, location: { lat: latlng.lat, lng: latlng.lng } } : s))
    );
    setResult(null);
  }, []);

  const handleRemoveStop = useCallback((id) => {
    setStops((prev) => prev.filter((s) => s.id !== id));
    setResult(null);
  }, []);

  const handleClear = useCallback(() => {
    setDepot(null);
    setStops([]);
    setResult(null);
    setError(null);
  }, []);

  const handleOptimize = useCallback(async () => {
    if (!depot || stops.length === 0) return;
    setIsOptimizing(true);
    setError(null);
    try {
      const payload = {
        depot,
        stops,
        end_strategy: endStrategy,
        departure_time: new Date().toISOString(),
        time_limit_seconds: 10,
      };
      const response = await optimizeRoute(payload);
      setResult(response);
    } catch (err) {
      setError(err.message || "Optimization failed. Is the backend running?");
      setResult(null);
    } finally {
      setIsOptimizing(false);
    }
  }, [depot, stops, endStrategy]);

  const optimizedOrder = result ? result.ordered_stops.map((e) => e.stop.id) : null;
  const routeGeometry = result ? result.geometry : null;

  return (
    <div className="app-shell">
      <Sidebar
        depot={depot}
        stops={stops}
        onSetDepotFromSearch={handleSetDepotFromSearch}
        onAddStopFromSearch={handleAddStopFromSearch}
        onRemoveStop={handleRemoveStop}
        onOptimize={handleOptimize}
        onClear={handleClear}
        endStrategy={endStrategy}
        onEndStrategyChange={setEndStrategy}
        isOptimizing={isOptimizing}
        error={error}
      />

      <main className="map-area">
        <MapView
          depot={depot}
          stops={stops}
          optimizedOrder={optimizedOrder}
          routeGeometry={routeGeometry}
          onDepotMove={handleDepotMove}
          onStopMove={handleStopMove}
          onMapClick={handleMapClick}
        />
      </main>

      <section className="results-panel">
        <RouteStats
          statistics={result ? result.statistics : null}
          algorithm={result ? result.algorithm : ""}
          solverStatus={result ? result.solver_status : ""}
        />
        <DeliveryList orderedStops={result ? result.ordered_stops : null} />
      </section>
    </div>
  );
}
