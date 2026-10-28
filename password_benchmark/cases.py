"""Expand the registered parameter grid into concrete configurations."""

import json
from dataclasses import dataclass, field


DISPLAY_NAMES = {
    "argon2id": "Argon2id",
    "bcrypt": "bcrypt",
    "pbkdf2_sha256": "PBKDF2-HMAC-SHA256",
    "scrypt": "scrypt",
}

PARAMETER_AXIS = {
    "memory_kib": "Memory (MiB)",
    "cost": "bcrypt cost",
    "iterations": "PBKDF2 iterations",
    "n": "scrypt N",
    "time_cost": "Argon2id time cost (t)",
}


@dataclass
class WorkCase:
    algorithm: str
    params: dict
    parameter_name: str
    parameter_value: int
    roles: tuple[str, ...]
    config_id: str
    tags: dict = field(default_factory=dict)


def display_name(algorithm: str) -> str:
    return DISPLAY_NAMES.get(algorithm, algorithm)


def parameter_axis_value(name: str, value: int) -> float:
    if name == "memory_kib":
        return value / 1024.0
    return float(value)


def configured_memory_bytes(params: dict) -> int | None:
    if "memory_kib" in params:
        return int(params["memory_kib"]) * 1024
    if "n" in params and "r" in params:
        # scrypt's V array; the per-lane B array (128*r*p bytes) is negligible.
        return 128 * int(params["n"]) * int(params["r"])
    return None


def make_config_id(algorithm: str, params: dict) -> str:
    if algorithm == "argon2id":
        return f"argon2id-m{params['memory_kib']}-t{params['time_cost']}-p{params['parallelism']}"
    if algorithm == "bcrypt":
        return f"bcrypt-c{params['cost']}"
    if algorithm == "pbkdf2_sha256":
        return f"pbkdf2-sha256-i{params['iterations']}"
    if algorithm == "scrypt":
        return f"scrypt-n{params['n']}-r{params['r']}-p{params['p']}"
    raise ValueError(f"Unknown algorithm: {algorithm}")


def case_record(case: WorkCase, design: str, config_sha256: str, experiment: str) -> dict:
    record = {
        "algorithm": case.algorithm,
        "config_id": case.config_id,
        "config_sha256": config_sha256,
        "design": design,
        "experiment": experiment,
        "parameter_name": case.parameter_name,
        "parameter_value": case.parameter_value,
        "params": dict(case.params),
        "roles": list(case.roles),
        "schema_version": 1,
    }
    if case.tags:
        record["tags"] = dict(case.tags)
    return record


def _canonical(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def build_cases(cfg) -> list[WorkCase]:
    cases: list[WorkCase] = []
    for algorithm, spec in cfg.algorithms.items():
        parameter = spec["sweep"]["parameter"]
        fixed = dict(spec["sweep"].get("fixed") or {})
        by_key: dict[str, dict] = {}
        order: list[str] = []
        for value in spec["sweep"]["values"]:
            params = dict(fixed)
            params[parameter] = int(value)
            key = _canonical(params)
            if key not in by_key:
                by_key[key] = {"params": params, "roles": ["sweep"]}
                order.append(key)
        baseline = {key: int(value) for key, value in spec["baseline"].items()}
        baseline_key = _canonical(baseline)
        if baseline_key in by_key:
            if "baseline" not in by_key[baseline_key]["roles"]:
                by_key[baseline_key]["roles"].append("baseline")
        else:
            by_key[baseline_key] = {"params": baseline, "roles": ["baseline"]}
            order.append(baseline_key)
        if parameter not in baseline:
            raise ValueError(f"{algorithm} baseline is missing {parameter}")
        for key in order:
            item = by_key[key]
            params = dict(item["params"])
            cases.append(
                WorkCase(
                    algorithm=algorithm,
                    params=params,
                    parameter_name=parameter,
                    parameter_value=int(params[parameter]),
                    roles=tuple(item["roles"]),
                    config_id=make_config_id(algorithm, params),
                )
            )
    identifiers = [case.config_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"Duplicate configuration ids: {identifiers}")
    return cases
