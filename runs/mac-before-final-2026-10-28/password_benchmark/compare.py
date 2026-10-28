"""Compare saved runs from different machines.

Reads only the tables that analyze wrote into runs/NAME/results. The machines
differ in processor, operating system, and Python build, so the comparison
reports rankings, ratios, and budget verdicts rather than absolute times.
"""

import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

from password_benchmark.analyze import _fmt, _md_table, _param_text, _write_csv
from password_benchmark.archive import RUN_NAME
from password_benchmark.cases import display_name
from password_benchmark.config import load_config
from password_benchmark.paths import ROOT
from password_benchmark.stats import meets_budget


def _number(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def _text_sha256(path: Path) -> str | None:
    # Line endings are normalized so a Windows checkout and a Mac checkout of one file agree.
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _table(path: Path) -> list[dict]:
    import pandas as pd

    if not path.is_file():
        return []
    return pd.read_csv(path).to_dict("records")


def load_run(name: str, root: Path = ROOT) -> dict:
    if not RUN_NAME.fullmatch(name):
        raise ValueError(f"Not a valid run name: {name}")
    folder = root / "runs" / name
    results = folder / "results"
    for path in (results / "rq1_baseline.csv", results / "environment.json"):
        if not path.is_file():
            raise FileNotFoundError(f"Missing saved run output: {path}")
    concurrent = _table(results / "rq3_concurrency.csv")
    return {
        "name": name,
        "environment": json.loads((results / "environment.json").read_text(encoding="utf-8")),
        "baselines": _table(results / "rq1_baseline.csv"),
        "sweep": _table(results / "rq2_parameter_sweep.csv"),
        "concurrent": concurrent,
        "equal_latency": _table(results / "supplementary" / "s5_equal_latency.csv"),
        # Runs collected before 2026-10-28 have no pool startup column.
        "corrected_harness": bool(concurrent) and "pool_startup_ms" in concurrent[0],
        "registered_text_sha256": _text_sha256(folder / "config" / "experiment.yaml"),
        "supplementary_text_sha256": _text_sha256(folder / "config" / "supplementary.yaml"),
    }


def _ratio(value, reference) -> float | None:
    if value is None or not reference:
        return None
    return value / reference


def _ratio_text(value) -> str:
    return "" if value is None else f"{value:.2f}x"


def _machine_rows(runs: list[dict]) -> list[list[str]]:
    rows = []
    for run in runs:
        env = run["environment"]
        processor = env.get("cpu_name") or ""
        if processor in {"", "arm", "i386"}:
            processor = f"{processor or 'unknown'} ({env.get('machine', '')}, name not recorded)"
        rows.append(
            [
                run["name"],
                processor,
                str(env.get("cpu_count_logical", "")),
                _fmt(env["ram_bytes"] / 1024**3, 0) + " GiB" if env.get("ram_bytes") else "",
                env.get("platform", ""),
                str(env.get("python", "")).split()[0],
                "corrected" if run["corrected_harness"] else "before 2026-10-28 corrections",
            ]
        )
    return rows


def _design_lines(runs: list[dict]) -> list[str]:
    lines = []
    recorded = {run["environment"].get("config_sha256") for run in runs}
    texts = {run["registered_text_sha256"] for run in runs}
    if len(recorded) == 1:
        lines.append(f"All runs used the same registered configuration (SHA-256 {recorded.pop()}).")
    elif len(texts) == 1 and None not in texts:
        lines.append(
            "The recorded configuration hashes differ, but the saved configuration files are identical after "
            "line-ending normalization. The difference comes from CRLF line endings on a Windows checkout."
        )
    else:
        lines.append("WARNING: the runs used different registered configurations. Do not compare them as replications.")
    with_supplementary = [run for run in runs if run["equal_latency"]]
    if len(with_supplementary) == len(runs):
        if len({run["supplementary_text_sha256"] for run in runs}) == 1:
            lines.append("All runs include the supplementary experiments with the same config/supplementary.yaml.")
        else:
            lines.append("WARNING: the runs used different config/supplementary.yaml files. Supplementary results are not comparable.")
    elif with_supplementary:
        lines.append("Only some runs include the supplementary experiments, so the supplementary comparison is omitted.")
    old = [run["name"] for run in runs if not run["corrected_harness"]]
    if old:
        lines.append(
            "Collected before the 2026-10-28 harness corrections: "
            + ", ".join(old)
            + ". Their process-pool checks include worker startup."
        )
    return lines


def _by_key(rows: list[dict], key: str) -> dict:
    return {row[key]: row for row in rows}


def _baseline_section(runs: list[dict]) -> tuple[list[str], list[dict]]:
    names = [run["name"] for run in runs]
    tables = [_by_key(run["baselines"], "algorithm") for run in runs]
    algorithms = [algorithm for algorithm in tables[0] if all(algorithm in table for table in tables)]
    csv_rows, md_rows = [], []
    for algorithm in algorithms:
        reference = _number(tables[0][algorithm]["median_ms"])
        cells = [display_name(algorithm)]
        for name, table in zip(names, tables):
            row = table[algorithm]
            median_ms, p95_ms = _number(row["median_ms"]), _number(row["p95_ms"])
            ratio = _ratio(median_ms, reference)
            csv_rows.append(
                {"algorithm": algorithm, "config_id": row["config_id"], "run": name, "median_ms": median_ms, "p95_ms": p95_ms, "median_ratio_to_first_run": ratio}
            )
            cells.append(f"{_fmt(median_ms)} / {_fmt(p95_ms)}")
        cells.extend(_ratio_text(_ratio(_number(table[algorithm]["median_ms"]), reference)) for table in tables[1:])
        md_rows.append(cells)
    headers = ["Algorithm"] + [f"{name} median / p95 ms" for name in names] + [f"{name} / {names[0]}" for name in names[1:]]
    lines = [_md_table(headers, md_rows), ""]

    orders = []
    for name, table in zip(names, tables):
        order = sorted(algorithms, key=lambda algorithm: _number(table[algorithm]["median_ms"]))
        orders.append(order)
        lines.append(f"- {name}: " + " < ".join(display_name(algorithm) for algorithm in order))
    agree = all(order == orders[0] for order in orders)
    lines.append(f"- Ranking by median verification time is {'the same' if agree else 'different'} on every machine.")
    lines.append("")

    pair_rows = []
    for faster, slower in combinations(orders[0], 2):
        cells = [f"{display_name(slower)} / {display_name(faster)}"]
        for table in tables:
            cells.append(_ratio_text(_ratio(_number(table[slower]["median_ms"]), _number(table[faster]["median_ms"]))))
        pair_rows.append(cells)
    lines.extend(
        [
            "Ratio of median verification times within each machine. A ratio that holds across machines does not depend "
            "on the hardware's absolute speed.",
            "",
            _md_table(["Pair"] + names, pair_rows),
            "",
        ]
    )
    return lines, csv_rows


def _sweep_section(runs: list[dict]) -> tuple[list[str], list[dict]]:
    names = [run["name"] for run in runs]
    tables = [_by_key(run["sweep"], "config_id") for run in runs]
    config_ids = [config_id for config_id in tables[0] if all(config_id in table for table in tables)]
    csv_rows, md_rows = [], []
    for config_id in config_ids:
        first = tables[0][config_id]
        reference = _number(first["median_ms"])
        cells = [display_name(first["algorithm"]), _param_text(first["parameter_name"], first["parameter_value"])]
        for name, table in zip(names, tables):
            median_ms = _number(table[config_id]["median_ms"])
            csv_rows.append(
                {
                    "algorithm": first["algorithm"],
                    "config_id": config_id,
                    "parameter_name": first["parameter_name"],
                    "parameter_value": first["parameter_value"],
                    "run": name,
                    "median_ms": median_ms,
                    "median_ratio_to_first_run": _ratio(median_ms, reference),
                }
            )
            cells.append(_fmt(median_ms))
        cells.extend(_ratio_text(_ratio(_number(table[config_id]["median_ms"]), reference)) for table in tables[1:])
        md_rows.append(cells)
    headers = ["Algorithm", "Parameter"] + [f"{name} median ms" for name in names] + [f"{name} / {names[0]}" for name in names[1:]]
    lines = [_md_table(headers, md_rows), ""]

    for algorithm in dict.fromkeys(tables[0][config_id]["algorithm"] for config_id in config_ids):
        ids = sorted((config_id for config_id in config_ids if tables[0][config_id]["algorithm"] == algorithm), key=lambda config_id: tables[0][config_id]["parameter_value"])
        if len(ids) < 2:
            continue
        low, high = tables[0][ids[0]], tables[0][ids[-1]]
        growth = [
            f"{_ratio_text(_ratio(_number(table[ids[-1]]['median_ms']), _number(table[ids[0]]['median_ms'])))} on {name}"
            for name, table in zip(names, tables)
        ]
        lines.append(
            f"- {display_name(algorithm)}, {_param_text(low['parameter_name'], low['parameter_value'])} to "
            f"{_param_text(high['parameter_name'], high['parameter_value'])}: " + ", ".join(growth) + "."
        )
    lines.append("")
    return lines, csv_rows


def _verdicts(row: dict, cfg) -> tuple[bool, bool] | None:
    p95_ms, throughput = _number(row.get("p95_ms")), _number(row.get("throughput_per_second"))
    if bool(row.get("skipped")) or p95_ms is None or throughput is None:
        return None
    return (
        meets_budget(p95_ms, throughput, cfg.budget_a_ms, cfg.throughput_min),
        meets_budget(p95_ms, throughput, cfg.budget_b_ms, cfg.throughput_min),
    )


def _verdict_text(verdict) -> str:
    if verdict is None:
        return "not measured"
    return "/".join("pass" if passed else "fail" for passed in verdict)


def _budget_section(runs: list[dict], cfg) -> tuple[list[str], list[dict]]:
    names = [run["name"] for run in runs]
    tables = []
    for run in runs:
        tables.append({row["config_id"]: row for row in run["concurrent"] if row["pool"] == "thread" and int(row["workers"]) == cfg.reference_workers})
    config_ids = [config_id for config_id in tables[0] if all(config_id in table for table in tables)]
    csv_rows, md_rows = [], []
    counts = {name: [0, 0] for name in names}
    agreeing = 0
    for config_id in config_ids:
        first = tables[0][config_id]
        cells = [display_name(first["algorithm"]), _param_text(first["parameter_name"], first["parameter_value"])]
        verdicts = []
        for name, table in zip(names, tables):
            row = table[config_id]
            verdict = _verdicts(row, cfg)
            verdicts.append(verdict)
            if verdict:
                counts[name][0] += verdict[0]
                counts[name][1] += verdict[1]
            csv_rows.append(
                {
                    "algorithm": first["algorithm"],
                    "config_id": config_id,
                    "run": name,
                    "workers": cfg.reference_workers,
                    "p95_ms": _number(row.get("p95_ms")),
                    "throughput_per_second": _number(row.get("throughput_per_second")),
                    "meets_a": None if verdict is None else verdict[0],
                    "meets_b": None if verdict is None else verdict[1],
                }
            )
            cells.append(f"{_fmt(_number(row.get('p95_ms')), 1)} ms, {_verdict_text(verdict)}")
        same = all(verdict == verdicts[0] for verdict in verdicts)
        agreeing += same
        cells.append("yes" if same else "no")
        md_rows.append(cells)
    headers = ["Algorithm", "Parameter"] + [f"{name} p95, A/B" for name in names] + ["Same verdict"]
    lines = [
        f"Thread pool with {cfg.reference_workers} workers. Budget A is p95 at most {cfg.budget_a_ms:g} ms and budget B at most "
        f"{cfg.budget_b_ms:g} ms, each with at least {cfg.throughput_min:g} verifications per second.",
        "",
        _md_table(headers, md_rows),
        "",
    ]
    for name in names:
        lines.append(f"- {name}: {counts[name][0]} of {len(config_ids)} meet budget A and {counts[name][1]} meet budget B.")
    lines.append(f"- The budget verdicts agree for {agreeing} of {len(config_ids)} configurations.")
    lines.append("")

    peak_rows = []
    for config_id in config_ids:
        first = tables[0][config_id]
        cells = [display_name(first["algorithm"]), _param_text(first["parameter_name"], first["parameter_value"])]
        for run in runs:
            measured = [
                row
                for row in run["concurrent"]
                if row["config_id"] == config_id and row["pool"] == "thread" and _number(row.get("throughput_per_second")) is not None
            ]
            best = max(measured, key=lambda row: row["throughput_per_second"], default=None)
            cells.append("" if best is None else f"{best['throughput_per_second']:.0f}/s at {int(best['workers'])}")
        peak_rows.append(cells)
    lines.extend(
        [
            "Highest registered thread-pool throughput and the worker count where it occurred. The worker count depends on "
            "each machine's core count.",
            "",
            _md_table(["Algorithm", "Parameter"] + names, peak_rows),
            "",
        ]
    )
    return lines, csv_rows


def _equal_latency_section(runs: list[dict]) -> list[str]:
    names = [run["name"] for run in runs]
    tables = [{(float(row["target_ms"]), row["algorithm"]): row for row in run["equal_latency"]} for run in runs]
    keys = [key for key in tables[0] if all(key in table for table in tables)]
    rows = []
    for target, algorithm in sorted(keys):
        cells = [f"{target:g}", display_name(algorithm)]
        for table in tables:
            row = table[(target, algorithm)]
            cells.append(f"{_param_text(row['parameter_name'], row['parameter_value'])} ({_fmt(_number(row['median_ms']), 1)} ms)")
        rows.append(cells)
    if not rows:
        return []
    return [
        "## Supplementary: equal verification time",
        "",
        "The parameter each machine reached for the same target time, with its measured median. A faster machine buys "
        "more work in the same time.",
        "",
        _md_table(["Target ms", "Algorithm"] + names, rows),
        "",
    ]


def compare_runs(names: list[str], root: Path = ROOT) -> Path:
    if len(names) < 2 or len(set(names)) != len(names):
        raise ValueError("Give at least two different saved run names.")
    runs = [load_run(name, root) for name in names]
    cfg = load_config()
    destination = root / "comparisons" / "__".join(names)
    destination.mkdir(parents=True, exist_ok=True)

    baseline_lines, baseline_rows = _baseline_section(runs)
    sweep_lines, sweep_rows = _sweep_section(runs)
    budget_lines, budget_rows = _budget_section(runs, cfg)
    _write_csv(destination / "comparison_rq1.csv", baseline_rows, list(baseline_rows[0]) if baseline_rows else [])
    _write_csv(destination / "comparison_rq2.csv", sweep_rows, list(sweep_rows[0]) if sweep_rows else [])
    _write_csv(destination / "comparison_rq3.csv", budget_rows, list(budget_rows[0]) if budget_rows else [])

    lines = [
        "# Cross-machine comparison",
        "",
        "Each run was analyzed on its own machine; this file only places their tables side by side. The machines differ "
        "in processor, operating system, and Python build, so a difference between them cannot be attributed to the "
        "operating system alone. Compare rankings, ratios, and budget verdicts rather than absolute times.",
        "",
        "## Machines",
        "",
        _md_table(["Run", "Processor", "Logical CPUs", "RAM", "Platform", "Python", "Harness"], _machine_rows(runs)),
        "",
    ]
    lines.extend(_design_lines(runs))
    lines.extend(["", "## Research question 1: baseline verification time", ""])
    lines.extend(baseline_lines)
    lines.extend(["## Research question 2: parameter sweeps", ""])
    lines.extend(sweep_lines)
    lines.extend(["## Research question 3: budgets at the reference load", ""])
    lines.extend(budget_lines)
    if all(run["equal_latency"] for run in runs) and len({run["supplementary_text_sha256"] for run in runs}) == 1:
        lines.extend(_equal_latency_section(runs))
    (destination / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    return destination
