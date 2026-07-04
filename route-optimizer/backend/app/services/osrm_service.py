"""
osrm_service.py
---------------
Wraps the OSRM (Open Source Routing Machine) HTTP API.

Why OSRM instead of straight-line (Haversine) distance?
---------------------------------------------------------
Haversine distance measures "as the crow flies" distance between two
points on a sphere. It ignores roads entirely, so it cannot tell the
difference between a location 500m away via a direct street and one
500m away but separated by a river with no bridge for 5km. For a
delivery driver, what matters is actual road distance and, more
importantly, actual drive TIME (which depends on road class, speed
limits, turns, and one-way restrictions) — not geometric distance.

OSRM pre-processes real OpenStreetMap road network data into a routing
graph and can answer two things we need:

1. Table service (`/table/v1/driving/...`)
   Given N coordinates, returns an NxN matrix of road distances and
   drive durations between every pair. This is exactly the "distance
   matrix" / "time matrix" that a TSP/VRP solver needs as its cost
   input. One call replaces what would otherwise be N^2 pathfinding
   requests.

2. Route service (`/route/v1/driving/...`)
   Given an ORDERED list of coordinates, returns the actual road
   geometry (as a polyline) connecting them in that order, plus total
   distance/duration. We call this only *after* OR-Tools has decided
   the optimal visiting order, purely to get the geometry to draw on
   the map and the final trip totals.

We default to the public demo server (router.project-osrm.org), which
is fine for prototyping but rate-limited and not for production use —
the request/response shape is identical if you point `base_url` at a
self-hosted OSRM instance (see docker-compose.yml).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import httpx

from app.models.schemas import LatLng

logger = logging.getLogger(__name__)

DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"


class OSRMError(Exception):
    """Raised when OSRM returns an error or an unroutable result."""


def _format_coordinates(locations: List[LatLng]) -> str:
    """OSRM expects 'lng,lat;lng,lat;...' — note lng comes first, not lat."""
    return ";".join(f"{loc.lng},{loc.lat}" for loc in locations)


async def get_distance_matrix(
    locations: List[LatLng], base_url: Optional[str] = None
) -> Tuple[List[List[float]], List[List[float]]]:
    """
    Call OSRM's Table service to build the full pairwise distance (meters)
    and duration (seconds) matrices for a list of locations.

    Returns:
        (distances_m, durations_s) — both are NxN lists of lists, where
        row i, col j = travel from locations[i] to locations[j].
    """
    base = (base_url or DEFAULT_OSRM_BASE_URL).rstrip("/")
    coords = _format_coordinates(locations)
    url = f"{base}/table/v1/driving/{coords}"
    params = {"annotations": "distance,duration"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("OSRM table request failed: %s", exc)
            raise OSRMError(f"OSRM table request failed: {exc}") from exc

    data = resp.json()
    if data.get("code") != "Ok":
        raise OSRMError(f"OSRM table service returned: {data.get('code')} - {data.get('message', '')}")

    distances = data.get("distances")
    durations = data.get("durations")
    if distances is None or durations is None:
        raise OSRMError("OSRM table response missing distances/durations")

    # OSRM can return null for pairs it cannot route between (e.g. islands
    # with no ferry link modeled). We fail loudly rather than silently
    # feeding None into the solver, since that would break the TSP model.
    for matrix, name in ((distances, "distances"), (durations, "durations")):
        for row in matrix:
            if any(v is None for v in row):
                raise OSRMError(
                    f"OSRM could not compute a route for one or more location pairs in the {name} "
                    "matrix. Check that all points are reachable by road."
                )

    return distances, durations


async def get_route_geometry(
    ordered_locations: List[LatLng], base_url: Optional[str] = None
) -> Tuple[List[LatLng], float, float]:
    """
    Call OSRM's Route service for an already-ordered list of stops to get
    the actual road geometry (for drawing on the map) plus total distance
    and duration for the full trip.

    Returns:
        (geometry_points, total_distance_m, total_duration_s)
    """
    base = (base_url or DEFAULT_OSRM_BASE_URL).rstrip("/")
    coords = _format_coordinates(ordered_locations)
    url = f"{base}/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("OSRM route request failed: %s", exc)
            raise OSRMError(f"OSRM route request failed: {exc}") from exc

    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise OSRMError(f"OSRM route service returned: {data.get('code')} - {data.get('message', '')}")

    route = data["routes"][0]
    coordinates = route["geometry"]["coordinates"]  # list of [lng, lat]
    geometry = [LatLng(lat=lat, lng=lng) for lng, lat in coordinates]

    return geometry, route["distance"], route["duration"]
