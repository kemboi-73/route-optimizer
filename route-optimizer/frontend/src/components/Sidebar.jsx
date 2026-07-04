import React, { useState } from "react";
import { geocode } from "../services/api";

export default function Sidebar({
  depot,
  stops,
  onSetDepotFromSearch,
  onAddStopFromSearch,
  onRemoveStop,
  onOptimize,
  onClear,
  endStrategy,
  onEndStrategyChange,
  isOptimizing,
  error,
}) {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState([]);
  const [searchTarget, setSearchTarget] = useState("stop"); // "depot" | "stop"

  async function runSearch(e) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setResults([]);
    try {
      const found = await geocode(query, 5);
      setResults(found);
    } catch (err) {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function pickResult(result) {
    if (searchTarget === "depot") {
      onSetDepotFromSearch(result);
    } else {
      onAddStopFromSearch(result);
    }
    setResults([]);
    setQuery("");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">◎</span>
        <div>
          <div className="brand-name">Routeon</div>
          <div className="brand-sub">Dispatch console</div>
        </div>
      </div>

      <form className="search-block" onSubmit={runSearch}>
        <div className="search-target-toggle">
          <button
            type="button"
            className={searchTarget === "depot" ? "toggle-btn active" : "toggle-btn"}
            onClick={() => setSearchTarget("depot")}
          >
            Set depot
          </button>
          <button
            type="button"
            className={searchTarget === "stop" ? "toggle-btn active" : "toggle-btn"}
            onClick={() => setSearchTarget("stop")}
          >
            Add stop
          </button>
        </div>
        <input
          className="search-input"
          placeholder='Search an address, e.g. "221B Baker Street"'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn-secondary" type="submit" disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </button>

        {results.length > 0 && (
          <ul className="search-results">
            {results.map((r) => (
              <li key={`${r.location.lat}-${r.location.lng}`}>
                <button type="button" onClick={() => pickResult(r)}>
                  {r.display_name}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="hint-text">Or click anywhere on the map to drop a stop.</p>
      </form>

      <div className="section-label">
        Depot
        <span className="count-pill">{depot ? "set" : "none"}</span>
      </div>
      <div className="depot-card">
        {depot ? (
          <span className="truncate">{depot.label || "Custom location"}</span>
        ) : (
          <span className="text-faint">No depot selected yet</span>
        )}
      </div>

      <div className="section-label">
        Delivery stops
        <span className="count-pill">{stops.length}</span>
      </div>
      <div className="stop-list">
        {stops.length === 0 && <div className="empty-state">No stops added yet.</div>}
        {stops.map((stop, idx) => (
          <div className="stop-row" key={stop.id}>
            <span className="stop-index">{idx + 1}</span>
            <span className="stop-label truncate">
              {stop.label || `${stop.location.lat.toFixed(4)}, ${stop.location.lng.toFixed(4)}`}
            </span>
            <button className="icon-btn" onClick={() => onRemoveStop(stop.id)} title="Remove stop">
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="section-label">Route end point</div>
      <div className="end-strategy">
        <label>
          <input
            type="radio"
            checked={endStrategy === "return_to_depot"}
            onChange={() => onEndStrategyChange("return_to_depot")}
          />
          Return to depot
        </label>
        <label>
          <input
            type="radio"
            checked={endStrategy === "end_at_last_stop"}
            onChange={() => onEndStrategyChange("end_at_last_stop")}
          />
          End at last stop
        </label>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="action-row">
        <button
          className="btn-primary"
          onClick={onOptimize}
          disabled={!depot || stops.length === 0 || isOptimizing}
        >
          {isOptimizing ? "Optimizing…" : "Optimize route"}
        </button>
        <button className="btn-ghost" onClick={onClear}>
          Clear all
        </button>
      </div>
    </aside>
  );
}
