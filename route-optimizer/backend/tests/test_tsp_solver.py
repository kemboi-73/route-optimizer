"""
Unit tests for the TSP solver. These use hand-constructed duration
matrices (no network calls / no OSRM needed) so they run fast and
deterministically in CI.
"""
import pytest

from app.optimization.tsp_solver import TSPSolverError, naive_tour_duration_s, solve_tsp


def test_solve_tsp_simple_square_returns_perimeter():
    """
    Four points forming a unit square (in seconds of travel time):
        0 --10-- 1
        |        |
        14       10
        |        |
        3 --10-- 2
    The optimal closed tour should traverse the perimeter (40), not a
    diagonal-crossing path (which would be longer).
    """
    matrix = [
        [0, 10, 14, 10],
        [10, 0, 10, 14],
        [14, 10, 0, 10],
        [10, 14, 10, 0],
    ]
    solution = solve_tsp(matrix, depot_index=0, return_to_depot=True, time_limit_seconds=5)
    assert solution.total_duration_s == 40
    assert len(solution.order) == 4
    assert solution.order[0] == 0
    assert set(solution.order) == {0, 1, 2, 3}


def test_solve_tsp_open_route_is_not_more_expensive_than_closed():
    matrix = [
        [0, 10, 14, 10],
        [10, 0, 10, 14],
        [14, 10, 0, 10],
        [10, 14, 10, 0],
    ]
    closed = solve_tsp(matrix, depot_index=0, return_to_depot=True, time_limit_seconds=5)
    open_ = solve_tsp(matrix, depot_index=0, return_to_depot=False, time_limit_seconds=5)
    assert open_.total_duration_s <= closed.total_duration_s


def test_solve_tsp_requires_at_least_two_locations():
    with pytest.raises(TSPSolverError):
        solve_tsp([[0]], depot_index=0, return_to_depot=True)


def test_naive_tour_duration_matches_entry_order():
    matrix = [
        [0, 5, 100],
        [5, 0, 5],
        [100, 5, 0],
    ]
    # naive: 0 -> 1 -> 2 -> back to 0 = 5 + 5 + 100 = 110
    assert naive_tour_duration_s(matrix, depot_index=0, return_to_depot=True) == 110
    # without return: 5 + 5 = 10
    assert naive_tour_duration_s(matrix, depot_index=0, return_to_depot=False) == 10


def test_solve_tsp_beats_or_matches_naive_on_a_harder_instance():
    """On a non-trivial matrix, OR-Tools' solution should never be worse
    than simply visiting stops in the order they were entered."""
    matrix = [
        [0, 29, 20, 21, 16],
        [29, 0, 15, 29, 28],
        [20, 15, 0, 15, 14],
        [21, 29, 15, 0, 4],
        [16, 28, 14, 4, 0],
    ]
    naive = naive_tour_duration_s(matrix, depot_index=0, return_to_depot=True)
    solution = solve_tsp(matrix, depot_index=0, return_to_depot=True, time_limit_seconds=5)
    assert solution.total_duration_s <= naive
