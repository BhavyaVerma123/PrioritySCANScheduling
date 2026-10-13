"""Run sample comparative workloads from the command line."""

from __future__ import annotations

import argparse

if __package__:
    from .disk_request import DiskRequest
    from .reporter import print_comparison
    from .schedulers import (
        Direction,
        PriorityAwareBurstScanScheduler,
        StandardScanScheduler,
    )
    from .simulator import run_simulation
else:
    from disk_request import DiskRequest
    from reporter import print_comparison
    from schedulers import (
        Direction,
        PriorityAwareBurstScanScheduler,
        StandardScanScheduler,
    )
    from simulator import run_simulation

def sample_workloads() -> dict[str, list[DiskRequest]]:
    """Return reproducible steady-traffic and heavy-burst workloads."""
    normal = [
        DiskRequest(f"N{index:02d}", track, index % 2, index * 3)
        for index, track in enumerate((42, 12, 88, 31, 67, 20, 95, 53, 8, 74))
    ]
    heavy_burst = [
        DiskRequest("B00", 25, 0, 0),
        DiskRequest("B01", 145, 1, 3),
        *[
            DiskRequest(f"B{index:02d}", track, index % 2, 10 + index)
            for index, track in enumerate(
                (112, 36, 158, 61, 127, 18, 93, 171, 48, 139), start=2
            )
        ],
        DiskRequest("B12", 72, 0, 28),
        DiskRequest("B13", 9, 1, 34),
        DiskRequest("B14", 184, 0, 41),
    ]
    return {"Normal traffic": normal, "Heavy burst phase": heavy_burst}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare standard SCAN with priority-aware SCAN, burst throttling, "
            "and starvation prevention."
        )
    )
    parser.add_argument("--max-track", type=int, default=199)
    parser.add_argument("--initial-head", type=int, default=50)
    parser.add_argument("--direction", choices=("up", "down"), default="up")
    parser.add_argument("--aging-factor", type=int, default=5)
    parser.add_argument("--burst-window", type=int, default=5)
    parser.add_argument("--burst-threshold", type=int, default=4)
    parser.add_argument("--max-consecutive-burst", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    direction: Direction = args.direction

    for workload_name, workload in sample_workloads().items():
        common = {
            "max_track": args.max_track,
            "initial_head": args.initial_head,
            "direction": direction,
            "burst_window": args.burst_window,
            "burst_threshold": args.burst_threshold,
            "max_consecutive_burst": args.max_consecutive_burst,
        }
        standard = run_simulation(
            workload, StandardScanScheduler(direction), **common
        )
        priority_aware = run_simulation(
            workload,
            PriorityAwareBurstScanScheduler(
                direction,
                aging_factor=args.aging_factor,
                max_consecutive_burst=args.max_consecutive_burst,
            ),
            **common,
        )
        print_comparison(workload_name, standard, priority_aware)


if __name__ == "__main__":
    main()
