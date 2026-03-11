import time
from collections import defaultdict
from typing import DefaultDict

class MetricsRegistry:
    """Simple in-memory metrics registry for M0 and simulation."""
    def __init__(self) -> None:
        self.counters: DefaultDict[str, int] = defaultdict(int)
        self.gauges: DefaultDict[str, float] = defaultdict(float)
        self.histograms: DefaultDict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        self.histograms[name].append(value)

    def measure_time(self, name: str):
        class Timer:
            def __init__(self, registry: "MetricsRegistry", metric_name: str):
                self.registry = registry
                self.name = metric_name
                self.start = 0.0

            def __enter__(self):
                self.start = time.perf_counter()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = (time.perf_counter() - self.start) * 1000.0  # ms
                self.registry.observe(self.name, duration)

        return Timer(self, name)


# Global singleton mainly for development purposes (if needed)
GLOBAL_METRICS = MetricsRegistry()
