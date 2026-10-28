"""Behavior of the selected bcrypt library past its 72-byte input limit."""

import importlib.metadata

import bcrypt

from password_benchmark.io_utils import append_jsonl, log_line, reset_file


def length_cases(lengths: list[int]) -> list[dict]:
    cases = []
    for length in lengths:
        password = b"a" * length
        alternate = None
        if length > 72:
            alternate = b"a" * 72 + b"b" * (length - 72)
        cases.append(
            {
                "name": f"ascii_{length}",
                "description": f"ASCII password of {length} bytes",
                "password": password,
                "alternate": alternate,
            }
        )
    cases.append(
        {
            "name": "prefix72_pair",
            "description": "Two ASCII passwords that share the first 72 bytes and differ afterwards",
            "password": b"a" * 72 + b"XXXX",
            "alternate": b"a" * 72 + b"YYYY",
        }
    )
    cases.append(
        {
            "name": "utf8_boundary",
            "description": (
                "UTF-8 passwords of 73 bytes whose final character starts at byte 71. "
                "The two final characters share the same first UTF-8 byte, so the first 72 bytes match."
            ),
            "password": ("a" * 71 + "\u00eb").encode("utf-8"),
            "alternate": ("a" * 71 + "\u00e9").encode("utf-8"),
        }
    )
    cases.append(
        {
            "name": "nul_inside_first_72",
            "description": "NUL byte inside a password shorter than 72 bytes, with a different continuation after the NUL",
            "password": b"a" * 10 + b"\x00" + b"b" * 20,
            "alternate": b"a" * 10 + b"\x00" + b"c" * 20,
            "nul_probe": b"a" * 10,
        }
    )
    return cases


def evaluate_bcrypt_lengths(cost: int, lengths: list[int]) -> list[dict]:
    version = importlib.metadata.version("bcrypt")
    records = []
    for case in length_cases(lengths):
        password = case["password"]
        alternate = case.get("alternate")
        record = {
            "alternate_bytes": None if alternate is None else len(alternate),
            "alternate_hex": None if alternate is None else alternate.hex(),
            "alternate_verify": None,
            "cost": cost,
            "description": case["description"],
            "error": None,
            "experiment": "bcrypt_length",
            "library_version": version,
            "name": case["name"],
            "password_bytes": len(password),
            "password_hex": password.hex(),
            "prefix72_verify": None,
            "schema_version": 1,
            "self_verify": None,
            "truncated_at_nul_verify": None,
        }
        try:
            encoded = bcrypt.hashpw(password, bcrypt.gensalt(rounds=cost))
            record["self_verify"] = bool(bcrypt.checkpw(password, encoded))
            if len(password) > 72:
                record["prefix72_verify"] = bool(bcrypt.checkpw(password[:72], encoded))
            if alternate is not None:
                record["alternate_verify"] = bool(bcrypt.checkpw(alternate, encoded))
            if "nul_probe" in case:
                record["truncated_at_nul_verify"] = bool(bcrypt.checkpw(case["nul_probe"], encoded))
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)
    return records


def run_bcrypt_length(cfg, raw_dir, results_dir, design: str) -> int:
    cost = int(cfg.algorithms["bcrypt"]["baseline"]["cost"])
    path = raw_dir / "bcrypt_length.jsonl"
    reset_file(path)
    records = evaluate_bcrypt_lengths(cost, cfg.bcrypt_lengths)
    for record in records:
        record["config_sha256"] = cfg.config_sha256
        record["design"] = design
        append_jsonl(path, record)
    problems = []
    for record in records:
        if record["password_bytes"] > 72:
            if record["error"] is None and record["self_verify"] is None:
                problems.append(record["name"])
        elif record["self_verify"] is not True:
            problems.append(record["name"])
    log_line(results_dir, f"bcrypt length phase finished. Cases: {len(records)}. Problems: {len(problems)}.")
    return 1 if problems else 0
