"""Throughput while several verifications run at the same time."""

import os
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import psutil

from password_benchmark.cases import build_cases, case_record, configured_memory_bytes
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.memory import probe_concurrent_rss, should_skip_for_memory
from password_benchmark.passwords import generate_passwords
from password_benchmark.timing import time_call

_PROCESS_HASHER = None
# Each warmup task sleeps this long so that every worker is still busy when the
# next warmup task is submitted. The executors then start a new worker per task.
_WARM_TASK_SECONDS = 0.2


def _init_process_hasher(algorithm: str, params: dict) -> None:
    global _PROCESS_HASHER
    _PROCESS_HASHER = make_hasher(algorithm, params)


def _process_verify(task: dict) -> dict:
    if _PROCESS_HASHER is None:
        raise RuntimeError("Process worker was not initialized")
    ok, wall_ns, _cpu_ns = time_call(lambda: _PROCESS_HASHER.verify(task["password"], task["encoded"]))
    return {"ok": ok, "password_id": task["password_id"], "verify_wall_ns": wall_ns}


def _process_ready(delay: float) -> int:
    time.sleep(delay)
    return os.getpid()


def _thread_ready(delay: float) -> int:
    time.sleep(delay)
    return threading.get_ident()


def _start_workers(executor, workers: int, identify) -> None:
    """Start every worker before the timed batch, so pool startup is not counted as throughput."""
    seen: set[int] = set()
    for _attempt in range(5):
        seen.update(executor.map(identify, [_WARM_TASK_SECONDS] * workers))
        if len(seen) >= workers:
            return
    raise RuntimeError(f"Only {len(seen)} of {workers} pool workers started before the timed batch")


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
    """Return results, batch wall ns, batch CPU seconds, and pool startup ns.

    Pool startup happens before the batch clock starts. It is recorded so the
    excluded cost stays visible.
    """
    if pool == "thread":
        hasher = make_hasher(case.algorithm, case.params)

        def verify_one(task: dict) -> dict:
            ok, wall_ns, _cpu_ns = time_call(lambda: hasher.verify(task["password"], task["encoded"]))
            return {"ok": ok, "password_id": task["password_id"], "verify_wall_ns": wall_ns}

        executor_factory = lambda: ThreadPoolExecutor(max_workers=workers)
        identify, verify = _thread_ready, verify_one
        map_options = {}
    else:
        executor_factory = lambda: ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_process_hasher,
            initargs=(case.algorithm, dict(case.params)),
        )
        identify, verify = _process_ready, _process_verify
        map_options = {"chunksize": 1}

    with executor_factory() as executor:
        startup_began = time.perf_counter_ns()
        _start_workers(executor, workers, identify)
        startup_ns = time.perf_counter_ns() - startup_began
        cpu_before = _tree_cpu_seconds()
        started = time.perf_counter_ns()
        results = list(executor.map(verify, jobs, **map_options))
        elapsed = time.perf_counter_ns() - started
        cpu_after = _tree_cpu_seconds()
    return results, elapsed, cpu_after - cpu_before, startup_ns


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
        results, batch_wall_ns, cpu_seconds, startup_ns = _execute(case, jobs, workers, pool)
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
                # Whole benchmark process tree, reused across configurations.
                # Earlier configurations can inflate it; see concurrent_memory.jsonl.
                "peak_rss": peak["rss"],
                "pool": pool,
                "pool_startup_ns": startup_ns,
                "skipped": False,
                "verify_wall_ns": result["verify_wall_ns"],
                "workers": workers,
            }
        )
        append_jsonl(path, record)
    if successes != verifications:
        raise RuntimeError(f"{case.config_id} completed {successes} of {verifications} verifications with the {pool} pool")


def _probe_memory(case, cfg, prepared, workers: int, design: str, path, results_dir) -> None:
    """Peak growth of a fresh process while `workers` verifications run at once."""
    memory_bytes = configured_memory_bytes(case.params) or 0
    if should_skip_for_memory(memory_bytes * workers, psutil.virtual_memory().available):
        record = case_record(case, design, cfg.config_sha256, "concurrent_memory")
        record.update({"reason": "insufficient_memory", "skipped": True, "workers": workers})
        append_jsonl(path, record)
        log_line(results_dir, f"Skipped {case.config_id} concurrent memory workers={workers}: insufficient memory")
        return
    for repeat in range(cfg.memory_repeats):
        tasks = [prepared[(repeat * workers + index) % len(prepared)] for index in range(workers)]
        probed = probe_concurrent_rss(case.algorithm, case.params, tasks)
        if not probed["ok"]:
            raise RuntimeError(f"Concurrent memory probe verification failed for {case.config_id}")
        record = case_record(case, design, cfg.config_sha256, "concurrent_memory")
        record.update(
            {
                "baseline_rss": probed["baseline_rss"],
                "configured_memory_bytes": configured_memory_bytes(case.params),
                "delta_rss": probed["delta_rss"],
                "ok": True,
                "peak_rss": probed["peak_rss"],
                "repeat": repeat,
                "skipped": False,
                "workers": workers,
            }
        )
        append_jsonl(path, record)


def run_concurrent(
    cfg,
    raw_dir,
    results_dir,
    design: str,
    cases=None,
    workers: list[int] | None = None,
    process_check: bool = True,
    memory_probe: bool = True,
    filename: str = "concurrent.jsonl",
    experiment: str = "concurrent",
) -> int:
    """Thread-pool batches at each worker count. With process_check, each baseline is also run
    in a process pool at the reference load. With memory_probe, a fresh process measures peak
    memory while the reference number of verifications run at once."""
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    cases = build_cases(cfg) if cases is None else cases
    worker_counts = cfg.concurrency_workers if workers is None else workers
    path = raw_dir / filename
    memory_path = raw_dir / filename.replace(".jsonl", "_memory.jsonl")
    error_path = raw_dir / "errors.jsonl"
    reset_file(path)
    if memory_probe:
        reset_file(memory_path)
    drop_experiment(error_path, experiment)
    failures = 0
    log_line(results_dir, f"Concurrency phase started ({filename}). Configurations: {len(cases)}.")
    for index, case in enumerate(cases, start=1):
        try:
            prepared = _prepare(case, passwords)
            for count in worker_counts:
                log_line(results_dir, f"[{index}/{len(cases)}] {case.config_id} threads={count}")
                _run_pool(case, cfg, prepared, count, cfg.concurrency_verifications, "thread", design, path, results_dir)
            if process_check and "baseline" in case.roles:
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
            if memory_probe:
                log_line(results_dir, f"[{index}/{len(cases)}] {case.config_id} fresh-process memory, {cfg.reference_workers} at once")
                _probe_memory(case, cfg, prepared, cfg.reference_workers, design, memory_path, results_dir)
        except Exception as exc:
            failures += 1
            append_jsonl(
                error_path,
                {
                    "config_id": case.config_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "experiment": experiment,
                    "traceback": traceback.format_exc(),
                },
            )
            log_line(results_dir, f"FAILED {case.config_id}: {type(exc).__name__}: {exc}")
    log_line(results_dir, f"Concurrency phase finished ({filename}). Failed configurations: {failures}.")
    return failures
