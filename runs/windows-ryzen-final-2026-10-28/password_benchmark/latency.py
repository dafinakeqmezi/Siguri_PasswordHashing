"""Sequential verification latency and external RSS measurement."""

import traceback
from dataclasses import dataclass

from password_benchmark.cases import build_cases, case_record, configured_memory_bytes
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.memory import probe_verify_rss
from password_benchmark.passwords import generate_passwords
from password_benchmark.stats import median
from password_benchmark.timing import time_call


@dataclass
class Prepared:
    password_id: int
    password: str
    byte_length: int
    encoded: str


def _record(case, design: str, config_sha256: str, **fields) -> dict:
    record = case_record(case, design, config_sha256, "latency")
    record.update(fields)
    return record


def run_latency(cfg, raw_dir, results_dir, design: str) -> int:
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    cases = build_cases(cfg)
    for case in cases:
        make_hasher(case.algorithm, case.params)

    latency_path = raw_dir / "latency.jsonl"
    memory_path = raw_dir / "memory.jsonl"
    error_path = raw_dir / "errors.jsonl"
    reset_file(latency_path)
    reset_file(memory_path)
    drop_experiment(error_path, "latency")
    reset_file(raw_dir / "passwords.jsonl")
    for item in passwords:
        append_jsonl(
            raw_dir / "passwords.jsonl",
            {
                "byte_length": item.byte_length,
                "char_length": item.char_length,
                "password": item.password,
                "password_id": item.password_id,
                "schema_version": 1,
                "seed": cfg.seed,
                "synthetic": True,
            },
        )

    log_line(results_dir, f"Latency phase started. Configurations: {len(cases)}. Passwords: {len(passwords)}.")
    failures = 0
    for index, case in enumerate(cases, start=1):
        try:
            run_case(cfg, case, passwords, design, latency_path, memory_path, results_dir, index, len(cases))
        except Exception as exc:
            failures += 1
            append_jsonl(
                error_path,
                {
                    "config_id": case.config_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "experiment": "latency",
                    "traceback": traceback.format_exc(),
                },
            )
            log_line(results_dir, f"FAILED {case.config_id}: {type(exc).__name__}: {exc}")
    log_line(results_dir, f"Latency phase finished. Failed configurations: {failures}.")
    return failures


def run_case(cfg, case, passwords, design, latency_path, memory_path, results_dir, index, total) -> None:
    hasher = make_hasher(case.algorithm, case.params)
    prepared: list[Prepared] = []
    for item in passwords:
        encoded, wall_ns, cpu_ns = time_call(lambda password=item.password: hasher.hash_password(password))
        prepared.append(Prepared(item.password_id, item.password, item.byte_length, encoded))
        append_jsonl(
            latency_path,
            _record(
                case,
                design,
                cfg.config_sha256,
                byte_length=item.byte_length,
                cpu_ns=cpu_ns,
                ok=True,
                operation="hash",
                password_id=item.password_id,
                phase="hash",
                repeat=0,
                wall_ns=wall_ns,
            ),
        )

    pilot_walls = []
    for repeat in range(cfg.pilot_repeats):
        ok, wall_ns, cpu_ns = time_call(lambda item=prepared[0]: hasher.verify(item.password, item.encoded))
        if not ok:
            raise RuntimeError(f"Pilot verification failed for {case.config_id}")
        pilot_walls.append(wall_ns)
        append_jsonl(
            latency_path,
            _record(
                case,
                design,
                cfg.config_sha256,
                byte_length=prepared[0].byte_length,
                cpu_ns=cpu_ns,
                ok=True,
                operation="verify",
                password_id=prepared[0].password_id,
                phase="pilot",
                repeat=repeat,
                wall_ns=wall_ns,
            ),
        )
    pilot_median_ms = median(pilot_walls) / 1e6
    reduced = pilot_median_ms > cfg.slow_threshold_ms
    repeats = cfg.slow_repeats if reduced else cfg.measured_repeats
    log_line(
        results_dir,
        f"[{index}/{total}] {case.config_id} pilot median {pilot_median_ms:.1f} ms, measured repeats {repeats}",
    )

    for repeat in range(cfg.warmup_repeats):
        ok, wall_ns, cpu_ns = time_call(lambda item=prepared[0]: hasher.verify(item.password, item.encoded))
        if not ok:
            raise RuntimeError(f"Warmup verification failed for {case.config_id}")
        append_jsonl(
            latency_path,
            _record(
                case,
                design,
                cfg.config_sha256,
                byte_length=prepared[0].byte_length,
                cpu_ns=cpu_ns,
                ok=True,
                operation="verify",
                password_id=prepared[0].password_id,
                phase="warmup",
                repeat=repeat,
                wall_ns=wall_ns,
            ),
        )

    measured = 0
    planned = len(prepared) * repeats
    for item in prepared:
        for repeat in range(repeats):
            ok, wall_ns, cpu_ns = time_call(lambda current=item: hasher.verify(current.password, current.encoded))
            if not ok:
                raise RuntimeError(f"Verification failed for {case.config_id} password {item.password_id}")
            append_jsonl(
                latency_path,
                _record(
                    case,
                    design,
                    cfg.config_sha256,
                    byte_length=item.byte_length,
                    cpu_ns=cpu_ns,
                    ok=True,
                    operation="verify",
                    password_id=item.password_id,
                    phase="measured",
                    pilot_median_ms=round(pilot_median_ms, 3),
                    reduced_sample=reduced,
                    repeat=repeat,
                    repeats_used=repeats,
                    wall_ns=wall_ns,
                ),
            )
            measured += 1
            if measured % 100 == 0 or measured == planned:
                log_line(results_dir, f"  {case.config_id}: {measured}/{planned} measured verifications")

    for repeat in range(cfg.memory_repeats):
        sample = prepared[repeat % len(prepared)]
        probed = probe_verify_rss(case.algorithm, case.params, sample.password, sample.encoded)
        if not probed["ok"]:
            raise RuntimeError(f"Memory probe verification failed for {case.config_id}")
        record = case_record(case, design, cfg.config_sha256, "memory")
        record.update(
            {
                "baseline_rss": probed["baseline_rss"],
                "configured_memory_bytes": configured_memory_bytes(case.params),
                "delta_rss": probed["delta_rss"],
                "ok": True,
                "password_id": sample.password_id,
                "peak_rss": probed["peak_rss"],
                "repeat": repeat,
            }
        )
        append_jsonl(memory_path, record)
