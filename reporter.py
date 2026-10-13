"""Console reporting for side-by-side scheduler comparisons."""

from __future__ import annotations

if __package__:
    from .simulator import SimulationResult
else:
    from simulator import SimulationResult


def _format(value: float) -> str:
    return f"{value:.2f}"


def print_comparison(
    workload_name: str,
    standard: SimulationResult,
    priority_aware: SimulationResult,
) -> None:
    """Print summary and per-priority metrics for a workload."""
    print(f"\n=== {workload_name} ===")
    print(
        f"{'Metric':<34} {'Standard SCAN':>18} "
        f"{'Priority-aware SCAN':>22}"
    )
    print("-" * 77)
    metrics = (
        ("Requests completed", "requests_completed"),
        ("Total head movement (tracks)", "total_head_movement"),
        ("Average seek time (ticks)", "average_seek_time"),
        ("Average waiting time (ticks)", "average_waiting_time"),
        ("Average response time (ticks)", "average_response_time"),
        ("Longest burst run", "max_consecutive_burst"),
        ("Burst fairness / cap compliance", "burst_fairness_percent"),
    )
    for label, attribute in metrics:
        left = getattr(standard.metrics, attribute)
        right = getattr(priority_aware.metrics, attribute)
        if attribute == "burst_fairness_percent":
            left = f"{_format(left)}%"
            right = f"{_format(right)}%"
        elif isinstance(left, float):
            left = _format(left)
            right = _format(right)
        print(f"{label:<34} {str(left):>18} {str(right):>22}")

    priorities = sorted(
        set(standard.metrics.priority_breakdown)
        | set(priority_aware.metrics.priority_breakdown)
    )
    if priorities:
        print("\nPer-priority service (base priority; larger is higher):")
        print(
            f"{'Priority':>8} {'Scheduler':<22} {'Completed':>10} "
            f"{'Avg wait':>12} {'Avg response':>14}"
        )
        for priority in priorities:
            for label, result in (
                ("Standard SCAN", standard),
                ("Priority-aware", priority_aware),
            ):
                value = result.metrics.priority_breakdown.get(priority)
                if value is None:
                    completed, waiting, response = 0, 0.0, 0.0
                else:
                    completed = value.requests_completed
                    waiting = value.average_waiting_time
                    response = value.average_response_time
                print(
                    f"{priority:>8} {label:<22} {completed:>10} "
                    f"{_format(waiting):>12} {_format(response):>14}"
                )

    print(
        "\nBurst fairness is a cap-compliance score: 100% means the longest "
        "observed burst streak did not exceed the configured cap."
    )
