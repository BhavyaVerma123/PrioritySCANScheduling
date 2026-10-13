"""Focused tests for SCAN ordering, aging, burst throttling, and metrics."""

import pytest

from PrioritySCANScheduling.disk_request import DiskRequest
from PrioritySCANScheduling.schedulers import (
    PriorityAwareBurstScanScheduler,
    StandardScanScheduler,
)
from PrioritySCANScheduling.simulator import run_simulation


def request(
    identifier: str, track: int, priority: int = 0, arrival: int = 0,
    burst: bool = False,
) -> DiskRequest:
    return DiskRequest(identifier, track, priority, arrival, burst)


def test_standard_scan_reverses_when_no_request_is_ahead() -> None:
    scheduler = StandardScanScheduler("up")
    chosen = scheduler.select_request([request("left", 12)], head=40, now=0)
    assert chosen.id == "left"
    assert scheduler.direction == "down"


def test_scan_reverses_from_lower_boundary_toward_remaining_requests() -> None:
    scheduler = StandardScanScheduler("down")
    boundary = scheduler.select_request([request("zero", 0)], head=0, now=0)
    assert boundary.id == "zero"

    upper = scheduler.select_request([request("upper", 20)], head=0, now=1)

    assert upper.id == "upper"
    assert scheduler.direction == "up"


@pytest.mark.parametrize("head,direction,track", [(0, "down", 0), (20, "up", 20)])
def test_requests_at_head_or_boundary_are_selectable(
    head: int, direction: str, track: int
) -> None:
    scheduler = StandardScanScheduler(direction)  # type: ignore[arg-type]
    chosen = scheduler.select_request([request("edge", track)], head=head, now=0)
    assert chosen.id == "edge"


def test_aging_allows_waiting_normal_request_to_overtake_fresh_high_priority() -> None:
    scheduler = PriorityAwareBurstScanScheduler(aging_factor=5)
    normal = request("normal", 12, priority=0, arrival=0)
    fresh_high = request("high", 14, priority=2, arrival=10)

    chosen = scheduler.select_request([normal, fresh_high], head=10, now=15)

    assert chosen.id == "normal"
    assert normal.effective_priority == 3


def test_burst_cap_yields_to_non_burst_request_ahead() -> None:
    scheduler = PriorityAwareBurstScanScheduler(max_consecutive_burst=2)
    bursts = [request("b1", 11, burst=True), request("b2", 12, burst=True)]
    scheduler.on_service_complete(bursts[0])
    scheduler.on_service_complete(bursts[1])
    other = request("normal", 13, priority=0, burst=False)
    next_burst = request("b3", 14, priority=10, burst=True)

    chosen = scheduler.select_request([next_burst, other], head=10, now=0)

    assert chosen.id == "normal"


def test_burst_throttle_reverses_to_yield_to_waiting_non_burst_request() -> None:
    scheduler = PriorityAwareBurstScanScheduler(max_consecutive_burst=1)
    scheduler.on_service_complete(request("b1", 1, burst=True))
    ahead_burst = request("b2", 15, burst=True)
    behind_normal = request("normal", 5, burst=False)

    chosen = scheduler.select_request(
        [ahead_burst, behind_normal], head=10, now=0
    )

    assert chosen.id == "normal"
    assert scheduler.direction == "down"


def test_simulation_metrics_account_for_movement_wait_and_burst_cap() -> None:
    workload = [
        request("normal", 8, priority=0, arrival=0),
        request("burst-1", 7, priority=1, arrival=0, burst=True),
        request("burst-2", 9, priority=1, arrival=0, burst=True),
    ]
    result = run_simulation(
        workload,
        PriorityAwareBurstScanScheduler(max_consecutive_burst=1),
        max_track=20,
        initial_head=5,
        burst_threshold=20,
        max_consecutive_burst=1,
    )

    assert result.metrics.requests_completed == 3
    assert result.metrics.total_head_movement == sum(
        record.seek_distance for record in result.records
    )
    assert result.metrics.total_head_movement == 4
    assert result.metrics.average_seek_time == pytest.approx(4 / 3)
    assert result.metrics.max_consecutive_burst == 1
    assert result.metrics.burst_fairness_percent == 100.0


def test_simulation_marks_dense_rolling_arrivals_as_burst() -> None:
    workload = [request(f"r{index}", 20 + index, arrival=index) for index in range(4)]
    result = run_simulation(
        workload,
        StandardScanScheduler(),
        max_track=40,
        burst_window=4,
        burst_threshold=4,
    )
    assert all(record.burst_flag for record in result.records)


def test_empty_workload_has_zero_metrics() -> None:
    result = run_simulation([], StandardScanScheduler(), max_track=20)
    assert result.metrics.requests_completed == 0
    assert result.metrics.total_head_movement == 0
    assert result.metrics.average_response_time == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_track": -1},
        {"max_track": 10, "initial_head": 11},
        {"max_track": 10, "burst_window": 0},
    ],
)
def test_invalid_simulation_parameters_are_rejected(kwargs: dict[str, int]) -> None:
    options = {"max_track": 10}
    options.update(kwargs)
    with pytest.raises(ValueError):
        run_simulation([], StandardScanScheduler(), **options)
