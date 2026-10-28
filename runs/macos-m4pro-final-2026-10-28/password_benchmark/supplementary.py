"""Supplementary experiments declared after the proposal.

config/supplementary.yaml adds to config/experiment.yaml and does not change it.
Output goes to data/raw/supplementary and results/supplementary, and every
table built from it is labeled supplementary.
"""

import copy
from dataclasses import dataclass

from password_benchmark.config import ExperimentConfig, file_sha256, load_config, smoke_config, yaml
from password_benchmark.paths import SUPPLEMENTARY_PATH

SUPPLEMENTARY_ALGORITHMS = ("argon2id", "scrypt")
WRONG_PASSWORD_ALGORITHMS = ("argon2id", "bcrypt", "pbkdf2_sha256", "scrypt")


@dataclass
class SupplementaryConfig:
    raw: dict
    sha256: str
    main: ExperimentConfig
    # The registered rules with the supplementary algorithms in place of the registered ones.
    extension: ExperimentConfig
    extra_workers: list[int]
    saturation_gain: float
    p95_growth_limit: float
    tight_budgets_ms: list[float]
    equal_latency: dict
    wrong_password: dict
    input_handling: dict
    bootstrap_resamples: int
    confidence: float
    statistics_seed: int

    def baselines(self) -> dict[str, dict]:
        """Baseline parameters of the registered algorithms and scrypt."""
        found = {name: dict(spec["baseline"]) for name, spec in self.main.algorithms.items()}
        found["scrypt"] = dict(self.extension.algorithms["scrypt"]["baseline"])
        return found


def _build(raw: dict, sha256: str, main: ExperimentConfig) -> SupplementaryConfig:
    algorithms = raw["algorithms"]
    if tuple(algorithms) != SUPPLEMENTARY_ALGORITHMS:
        raise ValueError(f"supplementary algorithms must be exactly {', '.join(SUPPLEMENTARY_ALGORITHMS)}")
    extension_raw = copy.deepcopy(main.raw)
    extension_raw["algorithms"] = copy.deepcopy(algorithms)
    extension = ExperimentConfig.from_dict(extension_raw, sha256, expected_algorithms=SUPPLEMENTARY_ALGORITHMS)
    concurrency = raw["concurrency"]
    extra_workers = [int(value) for value in concurrency["extra_workers"]]
    if any(value in main.concurrency_workers for value in extra_workers):
        raise ValueError("concurrency.extra_workers must not repeat the registered worker counts")
    statistics = raw["statistics"]
    confidence = float(statistics["confidence"])
    if not 0 < confidence < 1:
        raise ValueError("statistics.confidence must be between 0 and 1")
    equal_latency = raw["equal_latency"]
    if set(equal_latency["tune"]) != set(WRONG_PASSWORD_ALGORITHMS):
        raise ValueError(f"equal_latency.tune must cover {', '.join(WRONG_PASSWORD_ALGORITHMS)}")
    return SupplementaryConfig(
        raw=raw,
        sha256=sha256,
        main=main,
        extension=extension,
        extra_workers=extra_workers,
        saturation_gain=float(concurrency["saturation_gain"]),
        p95_growth_limit=float(concurrency["p95_growth_limit"]),
        tight_budgets_ms=[float(value) for value in raw["tight_budgets_ms"]],
        equal_latency=equal_latency,
        wrong_password=raw["wrong_password"],
        input_handling=raw["input_handling"],
        bootstrap_resamples=int(statistics["bootstrap_resamples"]),
        confidence=confidence,
        statistics_seed=int(statistics["seed"]),
    )


def load_supplementary(main: ExperimentConfig | None = None) -> SupplementaryConfig:
    if not SUPPLEMENTARY_PATH.exists():
        raise FileNotFoundError(f"Missing supplementary file: {SUPPLEMENTARY_PATH.name}")
    loaded = yaml.safe_load(SUPPLEMENTARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{SUPPLEMENTARY_PATH.name} must contain a mapping")
    return _build(loaded, file_sha256(SUPPLEMENTARY_PATH), main or load_config())


def smoke_supplementary(supp: SupplementaryConfig) -> SupplementaryConfig:
    """Small parameters for a pipeline check. This does not change the YAML file."""
    raw = copy.deepcopy(supp.raw)
    argon2 = raw["algorithms"]["argon2id"]
    argon2["baseline"].update({"memory_kib": 8192, "time_cost": 1})
    argon2["sweep"]["values"] = [1, 2]
    argon2["sweep"]["fixed"]["memory_kib"] = 8192
    scrypt = raw["algorithms"]["scrypt"]
    scrypt["baseline"]["n"] = 1024
    scrypt["sweep"]["values"] = [1024, 2048]
    raw["concurrency"]["extra_workers"] = [3]
    equal = raw["equal_latency"]
    equal.update({"targets_ms": [5], "measured_repeats": 1, "calibration_samples": 1, "calibration_rounds": 2})
    equal["tune"]["argon2id"]["start"] = 8192
    equal["tune"]["argon2id"]["fixed"]["time_cost"] = 1
    equal["tune"]["bcrypt"].update({"values": [4, 5, 6], "start": 4})
    equal["tune"]["pbkdf2_sha256"].update({"start": 2000, "step": 1000})
    equal["tune"]["scrypt"].update({"values": [1024, 2048, 4096], "start": 1024})
    raw["wrong_password"].update({"repeats": 1, "warmup": 1})
    raw["statistics"]["bootstrap_resamples"] = 200
    # The smoke corpus and repeat counts come from the smoke registered config.
    return _build(raw, supp.sha256, smoke_config(supp.main))
