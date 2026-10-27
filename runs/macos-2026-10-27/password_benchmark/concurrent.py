"""Throughput while several verifications run at the same time."""

import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import psutil

from password_benchmark.cases import build_cases, case_record, configured_memory_bytes
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.memory import should_skip_for_memory
from password_benchmark.passwords import generate_passwords
from password_benchmark.timing import time_call

_PROCESS_HASHER = None


def _init_process_hasher(algorithm: str, params: dict) -> None:
    global _PROCESS_HASHER
    _PROCESS_HASHER = make_hasher(algorithm, params)


def _process_verify(task: dict) -> dict:
    if _PROCESS_HASHER is None:
        raise RuntimeError("Process worker was not initialized")
    ok, wall_ns, _cpu_ns = time_call(lambda: _PROCESS_HASHER.verify(task["password"], task["encoded"]))
    return {"ok": ok, "password_id": task["password_id"], "verify_wall_ns": wall_ns}


def _prepare(case, passwords):
    hasher = make_hasher(case.algorithm, case.params)
    prepared = []
    for item in passwords:
        prepared.append(
            {
                "byte_length": item.byte_length,
                "encoded": hasher.hash_password(item.password),
                "password": item.password,
                "password_id": item.password_id,
            }
        )
    return prepared


def _jobs(prepared: list[dict], count: int) -> list[dict]:
    return [prepared[index % len(prepared)] for index in range(count)]


def _tree_rss() -> int:
    process = psutil.Process()
    total = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.Error:
            continue
    return total


def _tree_cpu_seconds() -> float:
    process = psutil.Process()
    times = process.cpu_times()
    total = times.user + times.system
    for child in process.children(recursive=True):
        try:
            child_times = child.cpu_times()
        except psutil.Error:
            continue
        total += child_times.user + child_times.system
    return total


def _execute(case, jobs: list[dict], workers: int, pool: str):
    if pool == "thread":
        hasher = make_hasher(case.algorithm, case.params)

        def verify_one(task: dict) -> dict:
            ok, wall_ns, _cpu_ns = time_call(lambda: hasher.verify(task["password"], task["encoded"]))
            return {"ok": ok, "password_id": task["password_id"], "verify_wall_ns": wall_ns}

        cpu_before = _tree_cpu_seconds()
        started = time.perf_counter_ns()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(verify_one, jobs))
        return results, time.perf_counter_ns() - started, _tree_cpu_seconds() - cpu_before

    cpu_holder = {}
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_process_hasher,
        initargs=(case.algorithm, dict(case.params)),
    ) as executor:
        cpu_holder["before"] = _tree_cpu_seconds()
        started = time.perf_counter_ns()
        results = list(executor.map(_process_verify, jobs, chunksize=1))
        elapsed = time.perf_counter_ns() - started
        cpu_holder["after"] = _tree_cpu_seconds()
    return results, elapsed, cpu_holder["after"] - cpu_holder["before"]


def _write_skip(case, cfg, design: str, path, workers: int, pool: str) -> None:
    record = case_record(case, design, cfg.config_sha256, "concurrent")
    record.update({"pool": pool, "reason": "insufficient_memory", "skipped": True, "workers": workers})
    append_jsonl(path, record)


def _run_pool(case, cfg, prepared, workers: int, verifications: int, pool: str, design: str, path, results_dir) -> None:
    memory_bytes = configured_memory_bytes(case.params) or 0
    if should_skip_for_memory(memory_bytes * workers, psutil.virtual_memory().available):
        _write_skip(case, cfg, design, path, workers, pool)
        log_line(results_dir, f"Skipped {case.config_id} {pool} workers={workers}: insufficient memory")
        return

    jobs = _jobs(prepared, verifications)
    peak = {"rss": _tree_rss()}
    stop_event = threading.Event()

    def sampler() -> None:
        while not stop_event.is_set():
            try:
                rss = _tree_rss()
            except psutil.Error:
                return
            if rss > peak["rss"]:
                peak["rss"] = rss
            stop_event.wait(0.005)

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()
    try:
        results, batch_wall_ns, cpu_seconds = _execute(case, jobs, workers, pool)
    finally:
        stop_event.set()
        sampler_thread.join(timeout=2)

    successes = 0
    for result in results:
        if result["ok"]:
            successes += 1
        record = case_record(case, design, cfg.config_sha256, "concurrent")
        record.update(
            {
                "batch_count": verifications,
                "batch_wall_ns": batch_wall_ns,
                "cpu_seconds": cpu_seconds,
                "ok": bool(result["ok"]),
                "password_id": result["password_id"],
                "peak_rss": peak["rss"],
                "pool": pool,
                "skipped": False,
                "verify_wall_ns": result["verify_wall_ns"],
                "workers": workers,
            }
        )
        append_jsonl(path, record)
    if successes != verifications:
        raise RuntimeError(f"{case.config_id} completed {successes} of {verifications} verifications with the {pool} pool")


def run_concurrent(cfg, raw_dir, results_dir, design: str) -> int:
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    cases = build_cases(cfg)
    path = raw_dir / "concurrent.jsonl"
    error_path = raw_dir / "errors.jsonl"
    reset_file(path)
    drop_experiment(error_path, "concurrent")
    failures = 0
    log_line(results_dir, f"Concurrency phase started. Configurations: {len(cases)}.")
    for index, case in enumerate(cases, start=1):
        try:
            prepared = _prepare(case, passwords)
            for workers in cfg.concurrency_workers:
                log_line(results_dir, f"[{index}/{len(cases)}] {case.config_id} threads={workers}")
                _run_pool(case, cfg, prepared, workers, cfg.concurrency_verifications, "thread", design, path, results_dir)
            if "baseline" in case.roles:
                log_line(results_dir, f"[{index}/{len(cases)}] {case.config_id} process-pool check")
                _run_pool(
                    case,
                    cfg,
                    prepared,
                    cfg.reference_workers,
                    cfg.process_pool_verifications,
                    "process",
                    design,
                    path,
                    results_dir,
                )
        except Exception as exc:
            failures += 1
            append_jsonl(
                error_path,
                {
                    "config_id": case.config_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "experiment": "concurrent",
                    "traceback": traceback.format_exc(),
                },
            )
            log_line(results_dir, f"FAILED {case.config_id}: {type(exc).__name__}: {exc}")
    log_line(results_dir, f"Concurrency phase finished. Failed configurations: {failures}.")
    return failures
