"""
routes.py
---------
HTTP API surface. Each endpoint is intentionally thin: it validates input
(via Pydantic), delegates to a service/optimization module, and shapes
the response. This keeps business logic testable independently of FastAPI.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    DistanceMatrixRequest,
    DistanceMatrixResponse,
    GeocodeRequest,
    GeocodeResult,
    LatLng,
    OptimizedStop,
    OptimizeRequest,
    OptimizeResponse,
    RouteEndStrategy,
    RouteGeometryRequest,
    RouteGeometryResponse,
    RouteStatistics,
)
from app.optimization.statistics import (
    compute_efficiency_score,
    compute_fuel_and_emissions,
    format_eta,
    parse_departure_time,
)
from app.optimization.tsp_solver import TSPSolverError, naive_tour_duration_s, solve_tsp
from app.services import osrm_service
from app.services.geocoder import GeocodingError, geocode_address

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/geocode", response_model=list[GeocodeResult], summary="Search for an address")
async def geocode(request: GeocodeRequest):
    """Forward-geocode a free-text address (e.g. '221B Baker Street') via Nominatim."""
    try:
        results = await geocode_address(request.query, request.limit)
    except GeocodingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not results:
        raise HTTPException(status_code=404, detail=f"No matches found for '{request.query}'")
    return results


@router.post(
    "/distance-matrix",
    response_model=DistanceMatrixResponse,
    summary="Build a road distance/duration matrix via OSRM's Table API",
)
async def distance_matrix(request: DistanceMatrixRequest):
    try:
        distances, durations = await osrm_service.get_distance_matrix(
            request.locations, request.osrm_base_url
        )
    except osrm_service.OSRMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DistanceMatrixResponse(distances_m=distances, durations_s=durations)


@router.post(
    "/route",
    response_model=RouteGeometryResponse,
    summary="Get real road geometry for an ordered list of stops via OSRM's Route API",
)
async def route(request: RouteGeometryRequest):
    try:
        geometry, distance_m, duration_s = await osrm_service.get_route_geometry(
            request.ordered_locations, request.osrm_base_url
        )
    except osrm_service.OSRMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RouteGeometryResponse(geometry=geometry, distance_m=distance_m, duration_s=duration_s)


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Full pipeline: geocode -> distance matrix -> TSP solve -> route geometry",
)
async def optimize(request: OptimizeRequest):
    """
    End-to-end optimization pipeline:

    1. Build the full location list: depot + all delivery stops.
    2. Call OSRM's Table API to get the real-road duration matrix.
    3. Feed that matrix to OR-Tools to find the minimum-time visiting order.
    4. Call OSRM's Route API on the *optimized* order to get map geometry
       and precise trip totals.
    5. Compute dispatcher-facing statistics (time saved, fuel, CO2, ETA).
    """
    all_stops = [request.depot] + request.stops
    locations = [s.location for s in all_stops]

    if len(locations) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 stops (plus depot) supported per route.")

    # Step 1: real-road duration matrix from OSRM
    try:
        distances_m, durations_s = await osrm_service.get_distance_matrix(locations, request.osrm_base_url)
    except osrm_service.OSRMError as exc:
        raise HTTPException(status_code=502, detail=f"Distance matrix failed: {exc}") from exc

    return_to_depot = request.end_strategy == RouteEndStrategy.RETURN_TO_DEPOT

    # Step 2: OR-Tools TSP solve over the duration matrix (we optimize for
    # time, not distance, since that's what actually matters to a driver).
    try:
        solution = solve_tsp(
            duration_matrix_s=durations_s,
            depot_index=0,
            return_to_depot=return_to_depot,
            time_limit_seconds=request.time_limit_seconds,
        )
    except TSPSolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ordered_stop_objs = [all_stops[i] for i in solution.order]
    ordered_locations = [s.location for s in ordered_stop_objs]
    if return_to_depot:
        ordered_locations_for_geometry = ordered_locations + [request.depot.location]
    else:
        ordered_locations_for_geometry = ordered_locations

    # Step 3: geometry + authoritative totals for the *actual* chosen order
    try:
        geometry, total_distance_m, total_duration_s = await osrm_service.get_route_geometry(
            ordered_locations_for_geometry, request.osrm_base_url
        )
    except osrm_service.OSRMError as exc:
        raise HTTPException(status_code=502, detail=f"Route geometry failed: {exc}") from exc

    # Step 4: per-leg breakdown + cumulative time for arrival estimates,
    # using the matrix (fast) rather than re-calling OSRM per leg.
    departure_dt = parse_departure_time(request.departure_time)
    cumulative_distance = 0.0
    cumulative_duration = 0.0
    optimized_stops: list[OptimizedStop] = []

    for i, node_idx in enumerate(solution.order):
        if i == 0:
            leg_distance = 0.0
            leg_duration = 0.0
        else:
            prev_idx = solution.order[i - 1]
            leg_distance = distances_m[prev_idx][node_idx]
            leg_duration = durations_s[prev_idx][node_idx]
            cumulative_distance += leg_distance
            cumulative_duration += leg_duration
            # Add service time at the previous stop (dwell time) so ETAs
            # reflect real dispatch behavior, not just drive time.
            cumulative_duration += all_stops[prev_idx].service_time_minutes * 60

        optimized_stops.append(
            OptimizedStop(
                stop=all_stops[node_idx],
                sequence_index=i,
                leg_distance_m=leg_distance,
                leg_duration_s=leg_duration,
                cumulative_distance_m=cumulative_distance,
                cumulative_duration_s=cumulative_duration,
                estimated_arrival=format_eta(departure_dt, cumulative_duration),
            )
        )

    # Step 5: statistics
    naive_duration = naive_tour_duration_s(durations_s, depot_index=0, return_to_depot=return_to_depot)
    efficiency = compute_efficiency_score(solution.total_duration_s, naive_duration)
    fuel_l, fuel_cost, co2_kg = compute_fuel_and_emissions(total_distance_m)
    avg_service = sum(s.service_time_minutes for s in request.stops) / max(len(request.stops), 1)

    stats = RouteStatistics(
        total_distance_m=total_distance_m,
        total_duration_s=total_duration_s,
        num_stops=len(request.stops),
        average_stop_service_minutes=round(avg_service, 1),
        estimated_completion_time=format_eta(departure_dt, cumulative_duration),
        naive_total_duration_s=naive_duration,
        time_saved_s=max(0.0, naive_duration - solution.total_duration_s),
        time_saved_percent=round(
            max(0.0, (naive_duration - solution.total_duration_s) / naive_duration * 100)
            if naive_duration > 0
            else 0.0,
            1,
        ),
        route_efficiency_score=efficiency,
        estimated_fuel_liters=fuel_l,
        estimated_fuel_cost=fuel_cost,
        estimated_co2_kg=co2_kg,
    )

    return OptimizeResponse(
        ordered_stops=optimized_stops,
        geometry=geometry,
        statistics=stats,
        solver_status=solution.status,
    )
