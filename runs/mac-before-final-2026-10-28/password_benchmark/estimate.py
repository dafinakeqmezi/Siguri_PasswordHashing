"""Rough wall-time estimate from a few verifications at the registered parameters."""

import json

from password_benchmark.cases import build_cases
from password_benchmark.hashers import make_hasher
from password_benchmark.passwords import generate_passwords
from password_benchmark.stats import median
from password_benchmark.timing import time_call


def _equivalent_calls(password_count: int, repeats: int, pilot: int, warmup: int, memory_repeats: int) -> int:
    # One hash per password is built before timing and is counted as one verification-equivalent.
    return password_count + pilot + warmup + (password_count * repeats) + memory_repeats


def run_estimate(cfg, results_dir) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    password = generate_passwords(1, cfg.password_lengths, cfg.charset, cfg.seed)[0].password
    grouped: dict[str, list] = {}
    for case in build_cases(cfg):
        grouped.setdefault(case.algorithm, []).append(case)

    samples = []
    print("Runtime estimate started. These timings are not experimental results.", flush=True)
    for algorithm, group in grouped.items():
        baseline = next(case for case in group if "baseline" in case.roles)
        hardest = max(group, key=lambda case: case.parameter_value)
        chosen = [baseline]
        if hardest.config_id != baseline.config_id:
            chosen.append(hardest)
        for case in chosen:
            hasher = make_hasher(case.algorithm, case.params)
            encoded = hasher.hash_password(password)
            hasher.verify(password, encoded)
            walls = []
            for _ in range(3):
                ok, wall_ns, _cpu_ns = time_call(lambda: hasher.verify(password, encoded))
                if not ok:
                    raise RuntimeError(f"Estimate verification failed for {case.config_id}")
                walls.append(wall_ns / 1e6)
            sample = {
                "algorithm": algorithm,
                "config_id": case.config_id,
                "is_baseline": "baseline" in case.roles,
                "median_ms": median(walls),
                "parameter_value": case.parameter_value,
            }
            samples.append(sample)
            print(f"  {case.config_id}: median {sample['median_ms']:.1f} ms over 3 verifications", flush=True)

    sequential_low = 0.0
    sequential_high = 0.0
    concurrent_low = 0.0
    concurrent_high = 0.0
    for algorithm, group in grouped.items():
        algorithm_samples = [sample for sample in samples if sample["algorithm"] == algorithm]
        baseline_ms = next(sample["median_ms"] for sample in algorithm_samples if sample["is_baseline"])
        highest_ms = max(sample["median_ms"] for sample in algorithm_samples)
        low_calls = _equivalent_calls(
            cfg.password_count,
            cfg.measured_repeats,
            cfg.pilot_repeats,
            cfg.warmup_repeats,
            cfg.memory_repeats,
        )
        high_repeats = cfg.slow_repeats if highest_ms > cfg.slow_threshold_ms else cfg.measured_repeats
        high_calls = _equivalent_calls(
            cfg.password_count,
            high_repeats,
            cfg.pilot_repeats,
            cfg.warmup_repeats,
            cfg.memory_repeats,
        )
        count = len(group)
        sequential_low += (baseline_ms / 1000.0) * low_calls * count
        sequential_high += (highest_ms / 1000.0) * high_calls * count
        for workers in cfg.concurrency_workers:
            concurrent_low += count * (cfg.concurrency_verifications * (baseline_ms / 1000.0) / workers)
            concurrent_high += count * cfg.concurrency_verifications * (highest_ms / 1000.0)
        concurrent_low += (cfg.process_pool_verifications * (baseline_ms / 1000.0) / cfg.reference_workers)
        concurrent_high += cfg.process_pool_verifications * (highest_ms / 1000.0)

    document = {
        "concurrent_high_seconds": concurrent_high,
        "concurrent_low_seconds": concurrent_low,
        "kind": "runtime_estimate",
        "note": (
            "Rough range only. The lower bound treats every configuration as being as fast as the baseline "
            "and assumes concurrency scales with the worker count. The upper bound treats every configuration "
            "as being as slow as the highest sampled point and assumes no parallel speedup. "
            "Process startup for the memory probes is not included. This file is not an experimental result."
        ),
        "samples": samples,
        "sequential_high_seconds": sequential_high,
        "sequential_low_seconds": sequential_low,
        "total_high_minutes": (sequential_high + concurrent_high) / 60.0,
        "total_low_minutes": (sequential_low + concurrent_low) / 60.0,
    }
    (results_dir / "runtime_estimate.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        "Rough full-run range: "
        f"{document['total_low_minutes']:.0f} to {document['total_high_minutes']:.0f} minutes. "
        "Expect the real run in the upper half of that range.",
        flush=True,
    )
