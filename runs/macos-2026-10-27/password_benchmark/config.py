"""Load the registered experiment file."""

import copy
import hashlib
from dataclasses import dataclass

from password_benchmark.paths import CONFIG_PATH

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised only without dependencies
    raise SystemExit("PyYAML is required. Install dependencies with: python -m pip install -r requirements-lock.txt") from exc


def file_sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise ValueError(f"Missing {where}.{key} in {CONFIG_PATH.name}")
    return mapping[key]


@dataclass
class ExperimentConfig:
    raw: dict
    config_sha256: str
    seed: int
    password_count: int
    password_lengths: list[int]
    charset: str
    warmup_repeats: int
    measured_repeats: int
    pilot_repeats: int
    slow_threshold_ms: float
    slow_repeats: int
    memory_repeats: int
    budget_a_ms: float
    budget_b_ms: float
    throughput_min: float
    reference_workers: int
    concurrency_workers: list[int]
    concurrency_verifications: int
    process_pool_verifications: int
    process_pool_agreement_ratio: float
    algorithms: dict
    bcrypt_lengths: list[int]

    @classmethod
    def from_dict(cls, raw: dict, config_sha256: str) -> "ExperimentConfig":
        passwords = _require(raw, "passwords", "experiment")
        budgets = _require(raw, "latency_budgets_ms", "experiment")
        throughput = _require(raw, "throughput", "experiment")
        concurrency = _require(raw, "concurrency", "experiment")
        algorithms = _require(raw, "algorithms", "experiment")
        bcrypt_length = _require(raw, "bcrypt_length", "experiment")

        password_count = int(_require(passwords, "count", "passwords"))
        lengths = [int(value) for value in _require(passwords, "lengths", "passwords")]
        charset = str(_require(passwords, "charset", "passwords"))
        workers = [int(value) for value in _require(concurrency, "workers", "concurrency")]
        reference_workers = int(_require(throughput, "reference_workers", "throughput"))
        agreement = float(_require(concurrency, "process_pool_agreement_ratio", "concurrency"))
        if not 0 < agreement < 1:
            raise ValueError("concurrency.process_pool_agreement_ratio must be between 0 and 1")

        if password_count < 1:
            raise ValueError("passwords.count must be at least 1")
        if not lengths or any(length < 1 for length in lengths):
            raise ValueError("passwords.lengths must contain positive integers")
        if not charset:
            raise ValueError("passwords.charset must not be empty")
        if not workers or any(worker < 1 for worker in workers):
            raise ValueError("concurrency.workers must contain positive integers")
        if reference_workers not in workers:
            raise ValueError("throughput.reference_workers must be one of concurrency.workers")
        expected = ("argon2id", "bcrypt", "pbkdf2_sha256")
        if tuple(algorithms) != expected:
            raise ValueError(f"algorithms must be exactly {', '.join(expected)} in that order")

        return cls(
            raw=raw,
            config_sha256=config_sha256,
            seed=int(_require(raw, "seed", "experiment")),
            password_count=password_count,
            password_lengths=lengths,
            charset=charset,
            warmup_repeats=int(_require(raw, "warmup_repeats", "experiment")),
            measured_repeats=int(_require(raw, "measured_repeats", "experiment")),
            pilot_repeats=int(_require(raw, "pilot_repeats", "experiment")),
            slow_threshold_ms=float(_require(raw, "slow_threshold_ms", "experiment")),
            slow_repeats=int(_require(raw, "slow_repeats", "experiment")),
            memory_repeats=int(_require(raw, "memory_repeats", "experiment")),
            budget_a_ms=float(_require(budgets, "A", "latency_budgets_ms")),
            budget_b_ms=float(_require(budgets, "B", "latency_budgets_ms")),
            throughput_min=float(_require(throughput, "minimum_per_second", "throughput")),
            reference_workers=reference_workers,
            concurrency_workers=workers,
            concurrency_verifications=int(_require(concurrency, "verifications", "concurrency")),
            process_pool_verifications=int(_require(concurrency, "process_pool_verifications", "concurrency")),
            process_pool_agreement_ratio=agreement,
            algorithms=algorithms,
            bcrypt_lengths=[int(value) for value in _require(bcrypt_length, "lengths", "bcrypt_length")],
        )


def load_config() -> ExperimentConfig:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing experiment file: {CONFIG_PATH.name}")
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{CONFIG_PATH.name} must contain a mapping")
    return ExperimentConfig.from_dict(loaded, file_sha256(CONFIG_PATH))


def smoke_config(cfg: ExperimentConfig) -> ExperimentConfig:
    """Small parameters for a pipeline check. This does not change the YAML file."""
    raw = copy.deepcopy(cfg.raw)
    raw["passwords"]["count"] = 2
    raw["passwords"]["lengths"] = [12]
    raw["warmup_repeats"] = 1
    raw["measured_repeats"] = 2
    raw["pilot_repeats"] = 1
    raw["slow_threshold_ms"] = 60000
    raw["slow_repeats"] = 1
    raw["memory_repeats"] = 1
    raw["throughput"]["reference_workers"] = 2
    raw["concurrency"]["workers"] = [1, 2]
    raw["concurrency"]["verifications"] = 4
    raw["concurrency"]["process_pool_verifications"] = 2

    raw["algorithms"]["argon2id"]["baseline"]["memory_kib"] = 8192
    raw["algorithms"]["argon2id"]["baseline"]["time_cost"] = 1
    raw["algorithms"]["argon2id"]["sweep"]["values"] = [8192]
    raw["algorithms"]["argon2id"]["sweep"]["fixed"]["time_cost"] = 1

    raw["algorithms"]["bcrypt"]["baseline"]["cost"] = 4
    raw["algorithms"]["bcrypt"]["sweep"]["values"] = [4]

    raw["algorithms"]["pbkdf2_sha256"]["baseline"]["iterations"] = 2000
    raw["algorithms"]["pbkdf2_sha256"]["sweep"]["values"] = [2000]
    return ExperimentConfig.from_dict(raw, cfg.config_sha256)
