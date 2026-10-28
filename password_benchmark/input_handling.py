"""Inputs that differ as bytes but derive the same key. Supplementary experiment.

HMAC replaces a key longer than the hash block (64 bytes for SHA-256) with its
digest, and pads a shorter key with zero bytes. PBKDF2-HMAC-SHA256 uses the
password as the HMAC key, and so does the PBKDF2 step inside scrypt. Each pair
here is derived with the same salt and parameters and the outputs are compared.
This records input handling only. It does not test password guessing.
"""

import hashlib
import importlib.metadata
import traceback

import bcrypt
from argon2.low_level import Type, hash_secret_raw

from password_benchmark.hashers import scrypt_maxmem
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, reset_file
from password_benchmark.supplementary import WRONG_PASSWORD_ALGORITHMS

SALT = bytes(range(16))


def _pattern(length: int) -> bytes:
    return bytes(97 + index % 26 for index in range(length))


def input_pairs(long_lengths: list[int], short_length: int) -> list[dict]:
    pairs = []
    for length in long_lengths:
        password = _pattern(length)
        pairs.append(
            {
                "name": f"sha256_of_{length}_bytes",
                "description": f"{length}-byte password and the 32-byte SHA-256 digest of that password",
                "password": password,
                "alternate": hashlib.sha256(password).digest(),
            }
        )
    password = _pattern(short_length)
    pairs.append(
        {
            "name": "trailing_nul",
            "description": f"{short_length}-byte password and the same password followed by one NUL byte",
            "password": password,
            "alternate": password + b"\x00",
        }
    )
    return pairs


def same_result(algorithm: str, params: dict, password: bytes, alternate: bytes) -> bool:
    if algorithm == "bcrypt":
        encoded = bcrypt.hashpw(password, bcrypt.gensalt(rounds=int(params["cost"])))
        return bool(bcrypt.checkpw(alternate, encoded))
    if algorithm == "pbkdf2_sha256":
        derive = lambda secret: hashlib.pbkdf2_hmac(
            "sha256", secret, SALT, int(params["iterations"]), dklen=int(params["hash_len"])
        )
    elif algorithm == "scrypt":
        n, r, p = int(params["n"]), int(params["r"]), int(params["p"])
        derive = lambda secret: hashlib.scrypt(
            secret, salt=SALT, n=n, r=r, p=p, maxmem=scrypt_maxmem(n, r, p), dklen=int(params["hash_len"])
        )
    elif algorithm == "argon2id":
        derive = lambda secret: hash_secret_raw(
            secret=secret,
            salt=SALT,
            time_cost=int(params["time_cost"]),
            memory_cost=int(params["memory_kib"]),
            parallelism=int(params["parallelism"]),
            hash_len=int(params["hash_len"]),
            type=Type.ID,
        )
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    return derive(password) == derive(alternate)


def evaluate_input_handling(baselines: dict[str, dict], long_lengths: list[int], short_length: int) -> list[dict]:
    versions = {
        "argon2id": f"argon2-cffi {importlib.metadata.version('argon2-cffi')}",
        "bcrypt": f"bcrypt {importlib.metadata.version('bcrypt')}",
        "pbkdf2_sha256": "hashlib (OpenSSL)",
        "scrypt": "hashlib (OpenSSL)",
    }
    records = []
    for algorithm in WRONG_PASSWORD_ALGORITHMS:
        for pair in input_pairs(long_lengths, short_length):
            record = {
                "algorithm": algorithm,
                "alternate_bytes": len(pair["alternate"]),
                "alternate_hex": pair["alternate"].hex(),
                "description": pair["description"],
                "error": None,
                "experiment": "input_handling",
                "library": versions[algorithm],
                "name": pair["name"],
                "params": dict(baselines[algorithm]),
                "password_bytes": len(pair["password"]),
                "password_hex": pair["password"].hex(),
                "same_result": None,
                "schema_version": 1,
            }
            try:
                record["same_result"] = same_result(algorithm, baselines[algorithm], pair["password"], pair["alternate"])
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
    return records


def run_input_handling(supp, raw_dir, results_dir, design: str) -> int:
    path = raw_dir / "input_handling.jsonl"
    error_path = raw_dir / "errors.jsonl"
    reset_file(path)
    drop_experiment(error_path, "input_handling")
    settings = supp.input_handling
    try:
        records = evaluate_input_handling(
            supp.baselines(), [int(value) for value in settings["long_lengths"]], int(settings["short_length"])
        )
    except Exception as exc:
        append_jsonl(
            error_path,
            {"config_id": "input_handling", "error": f"{type(exc).__name__}: {exc}", "experiment": "input_handling", "traceback": traceback.format_exc()},
        )
        log_line(results_dir, f"FAILED input handling: {type(exc).__name__}: {exc}")
        return 1
    for record in records:
        record["config_sha256"] = supp.sha256
        record["design"] = design
        append_jsonl(path, record)
    log_line(results_dir, f"Input-handling phase finished. Cases: {len(records)}.")
    return 0
