"""Calibrate every algorithm to the same median verification latency, then measure it.

This is a supplementary experiment. The registered baselines have different
costs, so this one asks what each algorithm buys for the same time.
"""

import math
import traceback
from dataclasses import replace

from password_benchmark.cases import WorkCase, make_config_id
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.latency import run_case
from password_benchmark.passwords import generate_passwords
from password_benchmark.stats import median
from password_benchmark.timing import time_call


def measure_median_ms(algorithm: str, params: dict, password: str, samples: int) -> float:
    hasher = make_hasher(algorithm, params)
    encoded = hasher.hash_password(password)
    if not hasher.verify(password, encoded):
        raise RuntimeError(f"Calibration verification failed for {algorithm} {params}")
    walls = []
    for _ in range(samples):
        ok, wall_ns, _cpu_ns = time_call(lambda: hasher.verify(password, encoded))
        if not ok:
            raise RuntimeError(f"Calibration verification failed for {algorithm} {params}")
        walls.append(wall_ns / 1e6)
    return median(walls)


def calibrate(spec: dict, target_ms: float, measure, rounds: int, tolerance: float) -> tuple[int, list[dict]]:
    """Choose the parameter value whose median latency is closest to target_ms.

    measure(value) returns a median in ms. "linear" parameters are rescaled in
    proportion to the remaining error. "doubling" parameters double the work at
    each step, so the nearest step and its neighbours are measured.
    """
    trail: list[dict] = []

    def probe(value: int) -> float:
        for item in trail:
            if item["value"] == value:
                return item["median_ms"]
        measured = float(measure(value))
        if measured <= 0:
            raise RuntimeError(f"Calibration measured {measured} ms for {value}")
        trail.append({"median_ms": measured, "value": value})
        return measured

    kind = spec["kind"]
    if kind == "linear":
        step = int(spec["step"])
        value = int(spec["start"])
        for _ in range(rounds):
            measured = probe(value)
            if abs(measured / target_ms - 1.0) <= tolerance:
                break
            proposed = max(step, int(round(value * target_ms / measured / step)) * step)
            if any(item["value"] == proposed for item in trail):
                break
            value = proposed
    elif kind == "doubling":
        values = [int(item) for item in spec["values"]]
        start = values.index(int(spec["start"]))
        measured = probe(values[start])
        guess = min(len(values) - 1, max(0, start + round(math.log2(target_ms / measured))))
        for candidate in (guess - 1, guess, guess + 1):
            if 0 <= candidate < len(values):
                probe(values[candidate])
    else:
        raise ValueError(f"Unknown calibration kind: {kind}")
    best = min(trail, key=lambda item: abs(math.log(item["median_ms"] / target_ms)))
    return best["value"], trail


def run_equal_latency(supp, raw_dir, results_dir, design: str) -> int:
    settings = supp.equal_latency
    cfg = replace(supp.main, measured_repeats=int(settings["measured_repeats"]), config_sha256=supp.sha256)
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    latency_path = raw_dir / "equal_latency.jsonl"
    memory_path = raw_dir / "equal_latency_memory.jsonl"
    calibration_path = raw_dir / "equal_latency_calibration.jsonl"
    error_path = raw_dir / "errors.jsonl"
    for path in (latency_path, memory_path, calibration_path):
        reset_file(path)
    drop_experiment(error_path, "equal_latency")

    targets = [float(value) for value in settings["targets_ms"]]
    total = len(targets) * len(settings["tune"])
    log_line(results_dir, f"Equal-latency phase started. Targets: {targets} ms.")
    failures = 0
    index = 0
    for target in targets:
        for algorithm, spec in settings["tune"].items():
            index += 1
            try:
                fixed = dict(spec.get("fixed") or {})
                parameter = spec["parameter"]

                def measure(value: int) -> float:
                    params = dict(fixed)
                    params[parameter] = int(value)
                    return measure_median_ms(algorithm, params, passwords[0].password, int(settings["calibration_samples"]))

                chosen, trail = calibrate(spec, target, measure, int(settings["calibration_rounds"]), float(settings["tolerance"]))
                for step, item in enumerate(trail):
                    append_jsonl(
                        calibration_path,
                        {
                            "algorithm": algorithm,
                            "chosen": item["value"] == chosen,
                            "config_sha256": supp.sha256,
                            "design": design,
                            "experiment": "equal_latency_calibration",
                            "median_ms": item["median_ms"],
                            "parameter_name": parameter,
                            "parameter_value": item["value"],
                            "step": step,
                            "target_ms": target,
                        },
                    )
                params = dict(fixed)
                params[parameter] = int(chosen)
                case = WorkCase(
                    algorithm=algorithm,
                    params=params,
                    parameter_name=parameter,
                    parameter_value=int(chosen),
                    roles=("equal_latency",),
                    config_id=f"eq{target:g}ms-{make_config_id(algorithm, params)}",
                    tags={"target_ms": target},
                )
                log_line(results_dir, f"[{index}/{total}] {algorithm} target {target:g} ms: {parameter}={chosen}")
                run_case(cfg, case, passwords, design, latency_path, memory_path, results_dir, index, total)
            except Exception as exc:
                failures += 1
                append_jsonl(
                    error_path,
                    {
                        "config_id": f"eq{target:g}ms-{algorithm}",
                        "error": f"{type(exc).__name__}: {exc}",
                        "experiment": "equal_latency",
                        "traceback": traceback.format_exc(),
                    },
                )
                log_line(results_dir, f"FAILED equal latency {algorithm} {target:g} ms: {type(exc).__name__}: {exc}")
    log_line(results_dir, f"Equal-latency phase finished. Failed configurations: {failures}.")
    return failures
