# Routeon — AI-Powered Delivery Route Optimizer

A production-style single-driver route optimization system, in the spirit of
how Amazon/UPS/DPD-style logistics engines plan a driver's day: given a
depot and a set of delivery stops, it computes the **minimum drive-time
sequence** using real road-network data — not straight-line distance.

```
Depot + up to 100 stops → OSRM (real road data) → OR-Tools (TSP solver) → optimized route + map + stats
```

![architecture](https://img.shields.io/badge/backend-FastAPI%20%2B%20OR--Tools-33d17a)
![architecture](https://img.shields.io/badge/frontend-React%20%2B%20Leaflet-33d17a)

---

## What it does

- Search addresses (OpenStreetMap Nominatim) and drop pins, or click the map directly.
- Set a depot, add 1–100 delivery stops, drag any pin to reposition it.
- Choose whether the route returns to the depot or ends at the last stop.
- Click **Optimize route** and the backend:
  1. Builds a real-road **drive-time matrix** between every stop pair via OSRM's Table API.
  2. Feeds that matrix into **Google OR-Tools** to solve the Traveling Salesman Problem.
  3. Fetches the actual road **route geometry** for the winning stop order via OSRM's Route API.
  4. Returns per-stop ETAs, total distance/time, time saved vs. a naive (as-entered) order, an
     efficiency score, and estimated fuel/CO₂.
- The map redraws with numbered, re-orderable markers and an animated route line.

---

## Why this isn't a shortest-distance / Haversine problem

Straight-line (Haversine) distance ignores the actual road network — one-way
streets, highways vs. side streets, rivers with no bridge nearby, speed
limits. Two points 500m apart as the crow flies might be a 5-minute drive or
a 20-minute detour depending on the roads between them. A dispatcher cares
about **drive time**, so:

- **OSRM** (Open Source Routing Machine) pre-processes real OpenStreetMap
  road graphs and answers "what's the actual road distance/time between
  these points" via its `/table` (many-to-many matrix) and `/route`
  (turn-by-turn path for an ordered list) endpoints.
- **OR-Tools** takes that real drive-time matrix and solves the ordering
  problem — Haversine distance never enters the optimization at all.

## The optimization problem: TSP, and why OR-Tools

Visiting N stops in the order that minimizes total time is the classic
**Traveling Salesman Problem**. It's **NP-hard** — the number of possible
visiting orders grows factorially (about 10¹⁸ for just 20 stops), so brute
force is only possible for a handful of stops. Google's **OR-Tools** solves
this with a two-phase strategy that's the industry-standard approach for
this class of problem:

1. **`PATH_CHEAPEST_ARC`** — a greedy construction heuristic that builds a
   feasible initial tour almost instantly by always extending the route with
   the cheapest next arc.
2. **`GUIDED_LOCAL_SEARCH`** — a metaheuristic that repeatedly applies local
   moves (2-opt, Or-opt, relocate) to improve the tour, using penalties on
   "stuck" arcs to escape local optima, for as long as the configured time
   budget allows (default 10s).

This reliably lands within a fraction of a percent of the true optimum for
10–100 stops in single-digit seconds — see `backend/app/optimization/tsp_solver.py`
for the fully commented implementation, and `backend/tests/test_tsp_solver.py`
for solver unit tests (no network required, run in CI).

The solver is structured around OR-Tools' **Vehicle Routing** API even
though only one vehicle is used today — see the "Extending to multi-vehicle
VRP" section below for how to grow it into a fleet router.

---

## Architecture

```
route-optimizer/
├── backend/                  FastAPI service
│   ├── app/
│   │   ├── main.py           App entrypoint, CORS, /health
│   │   ├── api/routes.py     /optimize /geocode /distance-matrix /route
│   │   ├── services/
│   │   │   ├── geocoder.py       Nominatim (address ⇄ lat/lng)
│   │   │   └── osrm_service.py   OSRM Table + Route API client
│   │   ├── optimization/
│   │   │   ├── tsp_solver.py     OR-Tools TSP/VRP-ready solver
│   │   │   └── statistics.py     Fuel/CO₂/efficiency-score estimation
│   │   └── models/schemas.py     Pydantic request/response contracts
│   ├── tests/test_tsp_solver.py
│   └── requirements.txt
│
├── frontend/                 React + Vite + Leaflet
│   └── src/
│       ├── App.jsx            State + layout
│       ├── components/
│       │   ├── MapView.jsx       Leaflet map, draggable numbered markers, route polyline
│       │   ├── Sidebar.jsx       Address search, depot/stop management, controls
│       │   ├── RouteStats.jsx    Distance/time/fuel/CO₂/efficiency cards
│       │   └── DeliveryList.jsx  Ordered stop-by-stop breakdown with ETAs
│       └── services/api.js       Backend REST client
│
├── docker-compose.yml
├── .env
└── README.md
```

### API endpoints (see interactive docs at `/docs` once running)

| Method | Path                | Purpose                                              |
|--------|---------------------|-------------------------------------------------------|
| POST   | `/api/optimize`      | Full pipeline: geocode → matrix → solve → geometry    |
| POST   | `/api/geocode`       | Address → candidate lat/lng results (Nominatim)       |
| POST   | `/api/distance-matrix` | Raw OSRM Table API pass-through (distance + duration) |
| POST   | `/api/route`         | Raw OSRM Route API pass-through (geometry for an ordered stop list) |
| GET    | `/health`            | Liveness probe                                        |

---

## Running it

### Option 1 — Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend + Swagger docs: http://localhost:8000/docs

### Option 2 — Run locally without Docker

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev    # http://localhost:5173, proxies /api -> localhost:8000
```

### Running backend tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

---

## Route statistics explained

| Metric | How it's derived |
|---|---|
| Total distance / time | From OSRM's Route API on the winning stop order |
| Time saved vs. naive order | Optimized total time vs. simply visiting stops in the order they were entered |
| Efficiency score (0–100) | Scaled improvement of optimized vs. naive duration |
| Estimated fuel / CO₂ | Distance-based estimate using configurable per-vehicle consumption and emissions factors (`backend/app/optimization/statistics.py`) — tune these constants for your fleet |
| ETA per stop | Departure time + cumulative drive time + cumulative dwell (service) time at prior stops |

---

## Extending to multi-vehicle VRP

The solver already uses OR-Tools' **Vehicle Routing** primitives
(`RoutingIndexManager`, `RoutingModel`) rather than a plain TSP library, so
scaling to a fleet is additive, not a rewrite:

- Set `num_vehicles > 1` in `RoutingIndexManager`.
- Add `routing.AddDimensionWithVehicleCapacity(...)` for load/capacity limits.
- Add a time dimension (`routing.AddDimension` on the duration matrix) plus
  `SetCumulVarSoftUpperBound` for delivery **time windows**.
- Add a break/lunch dimension via `SetBreakIntervalsOfVehicle`.

Hooks for priority and time-window fields already exist on the `Stop` model
(`priority`, `time_window_start/end`) — they're accepted by the API today
but not yet enforced in the solver, ready to be wired into a VRP dimension.

## Known limitations / production notes

- The public `router.project-osrm.org` demo server is used by default. It's
  rate-limited and unsuitable for production traffic — point `osrm_base_url`
  (per-request) or `OSRM_BASE_URL` at a self-hosted OSRM instance for real
  usage (see the commented `osrm` service in `docker-compose.yml`).
- Nominatim's usage policy caps public requests at ~1/sec; self-host it or
  use a commercial geocoder for high-volume dispatching.
- Fuel/CO₂ figures are estimates based on configurable averages, not live
  telematics — treat them as directional, not billing-grade.
- Not yet implemented from the "nice-to-have" list: PDF/CSV/GPX export,
  saved route history, dark-mode toggle (the UI ships dark-only today),
  and full multi-vehicle VRP — the architecture above is designed to make
  these additive.
