"""
tsp_solver.py
-------------
The optimization core: given a travel-time matrix, find the sequence of
stops that minimizes total driving time.

Background
----------
This is the Traveling Salesman Problem (TSP): given N locations and the
cost (here, drive time) to travel between every pair, find the order
that visits all of them exactly once (optionally returning to the
start) with minimum total cost.

TSP is NP-hard: the number of possible orderings grows factorially
(for 20 stops there are ~10^18 possible routes), so brute force is
impossible beyond a handful of stops. We need heuristics that find a
very good — usually optimal or near-optimal — solution in a bounded,
predictable amount of time.

Why Google OR-Tools
--------------------
OR-Tools is a mature, widely used combinatorial optimization library
that implements exactly this class of vehicle routing problem (its
routing module is literally called "Vehicle Routing" and treats TSP as
the single-vehicle special case). It gives us, out of the box:

  * RoutingIndexManager — maps between the solver's internal node
    indices and our own location indices (and handles multiple
    vehicles / depots for future VRP expansion).
  * RoutingModel — the constraint model: which arcs (edges) exist,
    their costs, and any additional constraints (capacity, time
    windows, etc. — hooks are included below for future use).
  * A two-phase solve strategy:
      1. PATH_CHEAPEST_ARC — a fast greedy construction heuristic that
         builds an initial feasible tour by repeatedly choosing the
         cheapest next arc. This gives the solver a decent starting
         point almost instantly.
      2. GUIDED_LOCAL_SEARCH — a metaheuristic that repeatedly applies
         local moves (2-opt, Or-opt, relocate, etc.) to improve the
         initial tour, using "penalties" to escape local optima instead
         of getting stuck, for as long as the time budget allows.

This combination reliably produces solutions within a fraction of a
percent of optimal for real-world stop counts (10-100 stops) within a
few seconds — which is why it's the standard approach used by real
logistics routing engines.

Vehicle Routing Problem (VRP) extension point
----------------------------------------------
This module is intentionally structured around OR-Tools' Vehicle
Routing API even though we currently solve for a single vehicle. To
extend to multiple vehicles (VRP) later: increase `num_vehicles` in
RoutingIndexManager, add vehicle capacity dimensions
(`AddDimensionWithVehicleCapacity`), and add time-window constraints
via `AddDimension` on the time matrix. The single-vehicle TSP solved
here is mathematically the m=1 special case of VRP.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

logger = logging.getLogger(__name__)


@dataclass
class TSPSolution:
    order: List[int]           # sequence of matrix indices, in visiting order (starts with depot)
    total_duration_s: float    # solver's objective value converted back to seconds
    status: str                # human-readable solver status


class TSPSolverError(Exception):
    """Raised when OR-Tools cannot find any feasible solution."""


def solve_tsp(
    duration_matrix_s: List[List[float]],
    depot_index: int = 0,
    return_to_depot: bool = True,
    time_limit_seconds: int = 10,
) -> TSPSolution:
    """
    Solve a single-vehicle TSP over a duration matrix (in seconds).

    Args:
        duration_matrix_s: NxN matrix, duration_matrix_s[i][j] = seconds to
            travel from location i to location j (from OSRM's Table API).
        depot_index: index (into the matrix) of the start/end location.
        return_to_depot: if True, the tour must return to the depot at the
            end (classic closed TSP tour). If False, the vehicle may end at
            any other stop — modeled here via an "open TSP" trick using a
            dummy zero-cost return arc, so the solver is free to end
            anywhere without being penalized for not returning.
        time_limit_seconds: how long OR-Tools may search for improvements
            before returning its best solution found so far.

    Returns:
        TSPSolution with the visiting order (list of matrix indices,
        starting at depot_index) and the total duration in seconds.
    """
    n = len(duration_matrix_s)
    if n < 2:
        raise TSPSolverError("Need at least 2 locations (depot + 1 stop) to optimize a route.")

    # OR-Tools' routing solver works with integer costs internally for
    # numerical stability, so we scale seconds up and round rather than
    # feeding it raw floats.
    SCALE = 1  # seconds are already a reasonable integer-ish unit
    matrix = [[int(round(v * SCALE)) for v in row] for row in duration_matrix_s]

    if not return_to_depot:
        # "Open" TSP trick: make every arc INTO the depot free (cost 0),
        # except we keep the OUT-of-depot arcs real. This lets the solver
        # treat "returning to depot" as costless, so it will naturally
        # choose to end the tour at whichever stop is cheapest to reach
        # last, rather than being forced back to the depot.
        for i in range(n):
            matrix[i][depot_index] = 0

    manager = pywrapcp.RoutingIndexManager(n, 1, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def duration_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    # Fast greedy construction heuristic for the initial tour.
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    # Metaheuristic that improves the initial tour via local search moves
    # (2-opt, Or-opt, relocate) while using penalties to escape local optima.
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(time_limit_seconds)
    search_parameters.log_search = False

    assignment = routing.SolveWithParameters(search_parameters)

    if assignment is None:
        raise TSPSolverError(
            "OR-Tools could not find a feasible route. This can happen if some "
            "stops are unreachable by road from the depot."
        )

    order: List[int] = []
    index = routing.Start(0)
    total_cost = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        order.append(node)
        previous_index = index
        index = assignment.Value(routing.NextVar(index))
        total_cost += routing.GetArcCostForVehicle(previous_index, index, 0)

    if not return_to_depot:
        # We zeroed-out the return arc above, so `total_cost` already
        # excludes it. `order` also excludes the final synthetic return to
        # depot_index, which is what we want for an open route.
        pass

    return TSPSolution(
        order=order,
        total_duration_s=float(total_cost),
        status="OPTIMAL" if routing.status() == routing_enums_pb2.FirstSolutionStrategy.UNSET else _status_name(routing),
    )


def _status_name(routing: "pywrapcp.RoutingModel") -> str:
    status_map = {
        0: "ROUTING_NOT_SOLVED",
        1: "ROUTING_SUCCESS",
        2: "ROUTING_FAIL",
        3: "ROUTING_FAIL_TIMEOUT",
        4: "ROUTING_INVALID",
    }
    return status_map.get(routing.status(), f"UNKNOWN({routing.status()})")


def naive_tour_duration_s(duration_matrix_s: List[List[float]], depot_index: int, return_to_depot: bool) -> float:
    """
    Compute the duration of the "naive" route: visit stops in the order
    they were entered (depot -> stop1 -> stop2 -> ... -> optionally depot).
    This is used purely as a baseline to compute "time saved" by
    optimization, mirroring how a dispatcher might otherwise just drive
    stops in the order a customer called them in.
    """
    n = len(duration_matrix_s)
    order = list(range(n))  # depot first (assumed index 0), then stops in given order
    total = 0.0
    for i in range(len(order) - 1):
        total += duration_matrix_s[order[i]][order[i + 1]]
    if return_to_depot:
        total += duration_matrix_s[order[-1]][depot_index]
    return total
