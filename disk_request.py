"""Disk I/O request model used by the scheduler simulations."""

from dataclasses import dataclass


@dataclass
class DiskRequest:
    """A request to access one track.

    ``priority`` is the request's base priority (larger values are more
    important). ``wait_time`` and ``effective_priority`` are updated by a
    scheduler when it considers the request.
    """

    id: str
    track: int
    priority: int
    arrival_time: int
    burst_flag: bool = False
    wait_time: int = 0
    effective_priority: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("request id must be a non-empty string")
        if isinstance(self.track, bool) or not isinstance(self.track, int):
            raise TypeError("track must be an integer")
        if self.track < 0:
            raise ValueError("track must be non-negative")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if isinstance(self.arrival_time, bool) or not isinstance(self.arrival_time, int):
            raise TypeError("arrival_time must be an integer")
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if not isinstance(self.burst_flag, bool):
            raise TypeError("burst_flag must be a boolean")
        if isinstance(self.wait_time, bool) or not isinstance(self.wait_time, int):
            raise TypeError("wait_time must be an integer")
        if self.wait_time < 0:
            raise ValueError("wait_time must be non-negative")
        if self.effective_priority is None:
            self.effective_priority = self.priority
        elif isinstance(self.effective_priority, bool) or not isinstance(
            self.effective_priority, int
        ):
            raise TypeError("effective_priority must be an integer")

    def update_effective_priority(self, now: int, aging_factor: int) -> int:
        """Refresh aging state and return the effective priority."""
        if isinstance(now, bool) or not isinstance(now, int):
            raise TypeError("now must be an integer")
        if (
            isinstance(aging_factor, bool)
            or not isinstance(aging_factor, int)
            or aging_factor <= 0
        ):
            raise ValueError("aging_factor must be positive")
        self.wait_time = max(0, now - self.arrival_time)
        self.effective_priority = self.priority + self.wait_time // aging_factor
        return self.effective_priority
