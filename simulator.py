"""Discrete-time request feeding, simulation execution, and metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Sequence

if __package__:
    from .disk_request import DiskRequest
    from .schedulers import Direction, ScanScheduler
else:
    from disk_request import DiskRequest
    from schedulers import Direction, ScanScheduler


@dataclass(frozen=True)
class ServiceRecord:
    request_id: str
    track: int
    priority: int
    effective_priority: int
    burst_flag: bool
    arrival_time: int
    service_start_time: int
    completion_time: int
    head_before: int
    seek_distance: int

    @property
    def waiting_time(self) -> int:
        return self.service_start_time - self.arrival_time

    @property
    def response_time(self) -> int:
        return self.completion_time - self.arrival_time


@dataclass(frozen=True)
class PriorityMetrics:
    requests_completed: int
    average_waiting_time: float
    average_response_time: float


@dataclass(frozen=True)
class SimulationMetrics:
    requests_completed: int
    total_head_movement: int
    average_seek_time: float
    average_waiting_time: float
    average_response_time: float
    max_consecutive_burst: int
    burst_fairness_percent: float
    priority_breakdown: dict[int, PriorityMetrics] = field(default_factory=dict)


@dataclass(frozen=True)
class SimulationResult:
    scheduler_name: str
    records: tuple[ServiceRecord, ...]
    metrics: SimulationMetrics
    final_head: int
    final_time: int


def mark_detected_bursts(
    requests: Sequence[DiskRequest], window: int, threshold: int
) -> list[DiskRequest]:
    """Copy requests and mark all arrivals in dense rolling-window bursts.

    A request is burst traffic if it is explicitly flagged or belongs to a
    rolling interval containing at least ``threshold`` arrivals.
    """
    if window <= 0 or threshold <= 0:
        raise ValueError("burst window and threshold must be positive")

    ordered = sorted(enumerate(requests), key=lambda item: (item[1].arrival_time, item[0]))
    burst_indexes: set[int] = set()
    left = 0
    for right, (_, request) in enumerate(ordered):
        while (
            left <= right
            and request.arrival_time - ordered[left][1].arrival_time >= window
        ):
            left += 1
        if right - left + 1 >= threshold:
            burst_indexes.update(index for index, _ in ordered[left : right + 1])

    copied: list[DiskRequest] = []
    for index, request in enumerate(requests):
        copy = replace(request, wait_time=0, effective_priority=request.priority)
        copy.burst_flag = copy.burst_flag or index in burst_indexes
        copied.append(copy)
    return copied


def calculate_metrics(
    records: Sequence[ServiceRecord], max_consecutive_burst: int
) -> SimulationMetrics:
    if max_consecutive_burst <= 0:
        raise ValueError("max_consecutive_burst must be positive")
    total = len(records)
    movement = sum(record.seek_distance for record in records)
    waiting_total = sum(record.waiting_time for record in records)
    response_total = sum(record.response_time for record in records)

    max_burst_run = current_burst_run = 0
    by_priority: dict[int, list[ServiceRecord]] = defaultdict(list)
    for record in records:
        by_priority[record.priority].append(record)
        if record.burst_flag:
            current_burst_run += 1
            max_burst_run = max(max_burst_run, current_burst_run)
        else:
            current_burst_run = 0

    fairness = 100.0
    if max_burst_run > max_consecutive_burst:
        fairness = 100.0 * max_consecutive_burst / max_burst_run

    priority_metrics = {
        priority: PriorityMetrics(
            requests_completed=len(priority_records),
            average_waiting_time=sum(
                record.waiting_time for record in priority_records
            )
            / len(priority_records),
            average_response_time=sum(
                record.response_time for record in priority_records
            )
            / len(priority_records),
        )
        for priority, priority_records in sorted(by_priority.items())
    }

    return SimulationMetrics(
        requests_completed=total,
        total_head_movement=movement,
        average_seek_time=movement / total if total else 0.0,
        average_waiting_time=waiting_total / total if total else 0.0,
        average_response_time=response_total / total if total else 0.0,
        max_consecutive_burst=max_burst_run,
        burst_fairness_percent=fairness,
        priority_breakdown=priority_metrics,
    )


def run_simulation(
    requests: Sequence[DiskRequest],
    scheduler: ScanScheduler,
    *,
    max_track: int,
    initial_head: int = 0,
    direction: Direction = "up",
    burst_window: int = 5,
    burst_threshold: int = 4,
    max_consecutive_burst: int = 3,
) -> SimulationResult:
    """Run a complete simulation using integer ticks and track-per-tick seeks.

    The head moves directly to a selected request (one tick per track moved).
    Arrivals during a seek become eligible when that seek completes. Queue
    exhaustion in the current direction causes a LOOK-style reversal.
    """
    if isinstance(max_track, bool) or not isinstance(max_track, int):
        raise TypeError("max_track must be an integer")
    if max_track < 0:
        raise ValueError("max_track must be non-negative")
    if isinstance(initial_head, bool) or not isinstance(initial_head, int):
        raise TypeError("initial_head must be an integer")
    if not 0 <= initial_head <= max_track:
        raise ValueError("initial_head must be within the disk bounds")
    if max_consecutive_burst <= 0:
        raise ValueError("max_consecutive_burst must be positive")
    identifiers = [request.id for request in requests]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("request ids must be unique within a simulation")
    if any(request.track > max_track for request in requests):
        raise ValueError("every request track must be within the disk bounds")

    scheduler.reset(direction)
    ordered = mark_detected_bursts(requests, burst_window, burst_threshold)
    ordered.sort(key=lambda request: request.arrival_time)
    pending: list[DiskRequest] = []
    records: list[ServiceRecord] = []
    next_arrival = 0
    now = 0
    head = initial_head

    while next_arrival < len(ordered) or pending:
        if not pending and next_arrival < len(ordered):
            now = max(now, ordered[next_arrival].arrival_time)

        while (
            next_arrival < len(ordered)
            and ordered[next_arrival].arrival_time <= now
        ):
            pending.append(ordered[next_arrival])
            next_arrival += 1

        selected = scheduler.select_request(pending, head, now)
        service_start = now
        distance = abs(selected.track - head)
        completion = now + distance

        while (
            next_arrival < len(ordered)
            and ordered[next_arrival].arrival_time <= completion
        ):
            pending.append(ordered[next_arrival])
            next_arrival += 1

        effective_priority = selected.effective_priority
        if effective_priority is None:
            effective_priority = selected.priority
        records.append(
            ServiceRecord(
                request_id=selected.id,
                track=selected.track,
                priority=selected.priority,
                effective_priority=effective_priority,
                burst_flag=selected.burst_flag,
                arrival_time=selected.arrival_time,
                service_start_time=service_start,
                completion_time=completion,
                head_before=head,
                seek_distance=distance,
            )
        )
        pending.remove(selected)
        scheduler.on_service_complete(selected)
        head = selected.track
        now = completion

    metrics = calculate_metrics(records, max_consecutive_burst)
    return SimulationResult(
        scheduler_name=type(scheduler).__name__,
        records=tuple(records),
        metrics=metrics,
        final_head=head,
        final_time=now,
    )
