"""
statistics.py
-------------
Derives human-facing route statistics (fuel, emissions, efficiency score,
ETAs) from the raw solver output. These are estimates for dispatcher
insight, not precise fleet-telemetry figures — coefficients are exposed
as constants so they can be tuned per vehicle type.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

# --- Tunable assumptions (typical light delivery van) ---------------------
AVG_FUEL_CONSUMPTION_L_PER_100KM = 9.5   # liters per 100km, diesel delivery van
FUEL_PRICE_PER_LITER = 1.75              # local currency units per liter
CO2_KG_PER_LITER_DIESEL = 2.68           # kg CO2 emitted per liter of diesel burned


def compute_fuel_and_emissions(total_distance_m: float) -> tuple[float, float, float]:
    """Return (fuel_liters, fuel_cost, co2_kg) for a given trip distance."""
    km = total_distance_m / 1000.0
    fuel_liters = (km / 100.0) * AVG_FUEL_CONSUMPTION_L_PER_100KM
    fuel_cost = fuel_liters * FUEL_PRICE_PER_LITER
    co2_kg = fuel_liters * CO2_KG_PER_LITER_DIESEL
    return round(fuel_liters, 2), round(fuel_cost, 2), round(co2_kg, 2)


def compute_efficiency_score(optimized_duration_s: float, naive_duration_s: float) -> float:
    """
    A 0-100 score representing how much better the optimized route is vs.
    the naive (entry-order) route. 100 = optimized route takes ~0 time
    relative to naive (unrealistic ceiling), 50 = optimized route is half
    the naive duration, 0 = no improvement at all.
    """
    if naive_duration_s <= 0:
        return 100.0
    improvement_ratio = 1.0 - (optimized_duration_s / naive_duration_s)
    score = max(0.0, min(1.0, improvement_ratio)) * 100.0
    # Even a route with no naive improvement possible (already optimal
    # ordering) is still a "good" route, so we floor the score at 60 when
    # the optimized route is not worse than naive.
    if optimized_duration_s <= naive_duration_s:
        score = max(score, 60.0)
    return round(score, 1)


def format_eta(departure: Optional[datetime], seconds_from_departure: float) -> Optional[str]:
    if departure is None:
        return None
    eta = departure + timedelta(seconds=seconds_from_departure)
    return eta.isoformat()


def parse_departure_time(departure_time: Optional[str]) -> Optional[datetime]:
    if not departure_time:
        return None
    try:
        return datetime.fromisoformat(departure_time)
    except ValueError:
        return None
