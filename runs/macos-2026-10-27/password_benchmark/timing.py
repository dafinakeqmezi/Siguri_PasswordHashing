"""Wall-clock and CPU timers for a single call."""

import time


def time_call(fn):
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    result = fn()
    wall_ns = time.perf_counter_ns() - wall_start
    cpu_ns = time.process_time_ns() - cpu_start
    return result, wall_ns, cpu_ns
