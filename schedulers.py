"""Standard and priority-aware SCAN disk schedulers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Sequence, TypeAlias

if __package__:
    from .disk_request import DiskRequest
else:
    from disk_request import DiskRequest

Direction: TypeAlias = Literal["up", "down"]


class ScanScheduler(ABC):
    """Shared direction handling for SCAN-family schedulers."""

    def __init__(self, direction: Direction = "up") -> None:
        self._validate_direction(direction)
        self.direction: Direction = direction

    @staticmethod
    def _validate_direction(direction: str) -> None:
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")

    def reset(self, direction: Direction) -> None:
        """Reset direction-dependent state before a simulation run."""
        self._validate_direction(direction)
        self.direction = direction

    def _requests_ahead(
        self, requests: Sequence[DiskRequest], head: int
    ) -> list[DiskRequest]:
        if self.direction == "up":
            return [request for request in requests if request.track >= head]
        return [request for request in requests if request.track <= head]

    def _ensure_directional_candidates(
        self, requests: Sequence[DiskRequest], head: int
    ) -> list[DiskRequest]:
        candidates = self._requests_ahead(requests, head)
        if not candidates:
            self.direction = "down" if self.direction == "up" else "up"
            candidates = self._requests_ahead(requests, head)
        return candidates

    @abstractmethod
    def select_request(
        self, requests: Sequence[DiskRequest], head: int, now: int
    ) -> DiskRequest:
        """Select the next request and update direction on queue reversals."""

    def on_service_complete(self, _: DiskRequest) -> None:
        """Record completion state used by policies with service streaks."""


class StandardScanScheduler(ScanScheduler):
    """SCAN/LOOK order: service the nearest request in the current direction."""

    def select_request(
        self, requests: Sequence[DiskRequest], head: int, now: int
    ) -> DiskRequest:
        del now
        if not requests:
            raise ValueError("cannot select from an empty request queue")
        candidates = self._ensure_directional_candidates(requests, head)
        return min(
            candidates,
            key=lambda request: (
                abs(request.track - head),
                request.arrival_time,
                request.id,
            ),
        )


class PriorityAwareBurstScanScheduler(ScanScheduler):
    """Directional SCAN with request aging and a consecutive-burst limit."""

    def __init__(
        self,
        direction: Direction = "up",
        aging_factor: int = 5,
        max_consecutive_burst: int = 3,
    ) -> None:
        super().__init__(direction)
        if aging_factor <= 0:
            raise ValueError("aging_factor must be positive")
        if max_consecutive_burst <= 0:
            raise ValueError("max_consecutive_burst must be positive")
        self.aging_factor = aging_factor
        self.max_consecutive_burst = max_consecutive_burst
        self.consecutive_burst_requests = 0

    def reset(self, direction: Direction) -> None:
        super().reset(direction)
        self.consecutive_burst_requests = 0

    def select_request(
        self, requests: Sequence[DiskRequest], head: int, now: int
    ) -> DiskRequest:
        if not requests:
            raise ValueError("cannot select from an empty request queue")
        candidates = self._requests_ahead(requests, head)
        if not candidates:
            self.direction = "down" if self.direction == "up" else "up"
            candidates = self._requests_ahead(requests, head)

        if self.consecutive_burst_requests >= self.max_consecutive_burst:
            non_burst_candidates = [
                request for request in candidates if not request.burst_flag
            ]
            if not non_burst_candidates:
                waiting_non_burst = [
                    request for request in requests if not request.burst_flag
                ]
                if waiting_non_burst:
                    self.direction = "down" if self.direction == "up" else "up"
                    candidates = self._requests_ahead(requests, head)
                    non_burst_candidates = [
                        request for request in candidates if not request.burst_flag
                    ]
            if non_burst_candidates:
                candidates = non_burst_candidates

        for request in candidates:
            request.update_effective_priority(now, self.aging_factor)

        return min(
            candidates,
            key=lambda request: (
                -(
                    request.effective_priority
                    if request.effective_priority is not None
                    else 0
                ),
                abs(request.track - head),
                request.arrival_time,
                request.id,
            ),
        )

    def on_service_complete(self, request: DiskRequest) -> None:
        if request.burst_flag:
            self.consecutive_burst_requests += 1
        else:
            self.consecutive_burst_requests = 0
