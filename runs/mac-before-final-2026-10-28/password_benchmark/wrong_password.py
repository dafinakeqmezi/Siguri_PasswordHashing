"""Verification time for the correct password and for a wrong one, at each baseline.

This is a supplementary experiment. The registered latency phase times only
successful verifications. A wrong password of the same length differs in its
last character, so both inputs take the same path up to the final comparison.
"""

import random
import traceback

from password_benchmark.cases import WorkCase, case_record, make_config_id
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.passwords import generate_passwords
from password_benchmark.supplementary import WRONG_PASSWORD_ALGORITHMS
from password_benchmark.timing import time_call


def wrong_variant(password: str, charset: str) -> str:
    """Same length; only the last character changes, to the next one in the charset."""
    last = password[-1]
    replacement = charset[(charset.index(last) + 1) % len(charset)] if last in charset else charset[0]
    if replacement == last:
        raise ValueError("The charset needs at least two characters")
    return password[:-1] + replacement


def interleaved_schedule(password_count: int, repeats: int, seed: int) -> list[tuple[int, str]]:
    schedule = [(index, kind) for index in range(password_count) for kind in ("correct", "wrong") for _ in range(repeats)]
    random.Random(seed).shuffle(schedule)
    return schedule


def run_wrong_password(supp, raw_dir, results_dir, design: str) -> int:
    cfg = supp.main
    settings = supp.wrong_password
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    path = raw_dir / "wrong_password.jsonl"
    error_path = raw_dir / "errors.jsonl"
    reset_file(path)
    drop_experiment(error_path, "wrong_password")
    baselines = supp.baselines()
    log_line(results_dir, "Wrong-password timing phase started.")
    failures = 0
    for position, algorithm in enumerate(WRONG_PASSWORD_ALGORITHMS, start=1):
        params = baselines[algorithm]
        case = WorkCase(
            algorithm=algorithm,
            params=params,
            parameter_name="",
            parameter_value=0,
            roles=("baseline",),
            config_id=make_config_id(algorithm, params),
        )
        try:
            hasher = make_hasher(algorithm, params)
            encoded = [hasher.hash_password(item.password) for item in passwords]
            wrong = [wrong_variant(item.password, cfg.charset) for item in passwords]
            for _ in range(int(settings["warmup"])):
                hasher.verify(passwords[0].password, encoded[0])
            schedule = interleaved_schedule(len(passwords), int(settings["repeats"]), cfg.seed + position)
            log_line(results_dir, f"[{position}/{len(WRONG_PASSWORD_ALGORITHMS)}] {case.config_id}: {len(schedule)} verifications")
            for order, (index, kind) in enumerate(schedule):
                candidate = passwords[index].password if kind == "correct" else wrong[index]
                result, wall_ns, cpu_ns = time_call(lambda: hasher.verify(candidate, encoded[index]))
                if result is not (kind == "correct"):
                    raise RuntimeError(f"{case.config_id}: {kind} password returned {result}")
                record = case_record(case, design, supp.sha256, "wrong_password")
                record.update(
                    {
                        "byte_length": passwords[index].byte_length,
                        "cpu_ns": cpu_ns,
                        "kind": kind,
                        "order": order,
                        "password_id": passwords[index].password_id,
                        "result": bool(result),
                        "wall_ns": wall_ns,
                    }
                )
                append_jsonl(path, record)
        except Exception as exc:
            failures += 1
            append_jsonl(
                error_path,
                {
                    "config_id": case.config_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "experiment": "wrong_password",
                    "traceback": traceback.format_exc(),
                },
            )
            log_line(results_dir, f"FAILED {case.config_id}: {type(exc).__name__}: {exc}")
    log_line(results_dir, f"Wrong-password timing phase finished. Failed configurations: {failures}.")
    return failures
