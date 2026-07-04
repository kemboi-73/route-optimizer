"""
geocoder.py
-----------
Wraps OpenStreetMap's Nominatim geocoding service.

Nominatim converts free-text addresses ("221B Baker Street") into
lat/lng coordinates, and can also do the reverse (coordinates -> address).

We use the public https://nominatim.openstreetmap.org endpoint by default.
Nominatim's usage policy requires:
  * a descriptive User-Agent header (required, requests are rejected otherwise)
  * no more than ~1 request/second (we do not batch-geocode in a tight loop)
  * results are cached client-side where possible

For production use at scale, self-host Nominatim or use a commercial
provider and swap the base URL / headers here.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from app.models.schemas import GeocodeResult, LatLng

logger = logging.getLogger(__name__)

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "route-optimizer-app/1.0 (contact: admin@example.com)"


class GeocodingError(Exception):
    """Raised when the geocoding provider fails or returns no usable data."""


async def geocode_address(query: str, limit: int = 5) -> List[GeocodeResult]:
    """
    Forward geocode a free-text address into candidate lat/lng results.

    Returns results ordered by Nominatim's own relevance ("importance") score,
    most relevant first.
    """
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": str(limit),
        "addressdetails": "0",
    }
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{NOMINATIM_BASE_URL}/search", params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Nominatim geocoding failed for query=%r: %s", query, exc)
            raise GeocodingError(f"Geocoding request failed: {exc}") from exc

    data = resp.json()
    if not data:
        return []

    results: List[GeocodeResult] = []
    for item in data:
        try:
            results.append(
                GeocodeResult(
                    display_name=item["display_name"],
                    location=LatLng(lat=float(item["lat"]), lng=float(item["lon"])),
                    place_id=str(item.get("place_id")) if item.get("place_id") else None,
                    importance=item.get("importance"),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed Nominatim result: %s (%s)", item, exc)

    return results


async def reverse_geocode(location: LatLng) -> Optional[str]:
    """Reverse geocode a coordinate into a human-readable address string."""
    params = {"lat": str(location.lat), "lon": str(location.lng), "format": "jsonv2"}
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{NOMINATIM_BASE_URL}/reverse", params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Nominatim reverse geocoding failed: %s", exc)
            return None

    data = resp.json()
    return data.get("display_name")
