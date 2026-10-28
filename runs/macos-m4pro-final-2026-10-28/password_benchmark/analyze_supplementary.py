"""Tables, figures, and summary for the supplementary experiments.

Everything written here is labeled supplementary. The registered answers to
the three research questions stay in results/summary.md.
"""

import json
from pathlib import Path

from password_benchmark.analyze import (
    COLORS,
    MIB,
    _attach_intervals,
    _attach_memory,
    _baseline_table,
    _baseline_tests,
    _budget_rows,
    _check_design,
    _ci_text,
    _concurrent_memory_index,
    _concurrent_table,
    _fmt,
    _fmt_p,
    _latency_table,
    _md_table,
    _memory_index,
    _param_text,
    _plot_rq2,
    _process_pool_lines,
    _save,
    _seed_for,
    _style,
    _sweep_lines,
    _test_lines,
    _write_csv,
)
from password_benchmark.cases import display_name
from password_benchmark.io_utils import read_jsonl
from password_benchmark.stats import bootstrap_median_contrast_ci, cliffs_magnitude, mann_whitney, median, meets_budget
from password_benchmark.supplementary import WRONG_PASSWORD_ALGORITHMS

ALGORITHM_ORDER = {name: index for index, name in enumerate(WRONG_PASSWORD_ALGORITHMS)}


def _statistics(supp) -> dict:
    return {"bootstrap_resamples": supp.bootstrap_resamples, "confidence": supp.confidence, "seed": supp.statistics_seed}


def saturation_point(points: list[dict], gain: float, growth: float) -> tuple[int, str] | None:
    """First worker count where throughput stops rising by `gain` or p95 exceeds `growth` x the 1-worker p95."""
    measured = sorted((row for row in points if not row["skipped"]), key=lambda row: row["workers"])
    if len(measured) < 2 or measured[0]["workers"] != 1:
        return None
    single_p95 = measured[0]["p95_ms"]
    for previous, current in zip(measured, measured[1:]):
        reasons = []
        if current["throughput_per_second"] < previous["throughput_per_second"] * (1.0 + gain):
            reasons.append(f"throughput rose less than {gain:.0%} over {previous['workers']} workers")
        if current["p95_ms"] > growth * single_p95:
            reasons.append(f"p95 exceeded {growth:g}x the 1-worker p95")
        if reasons:
            return current["workers"], "; ".join(reasons)
    return None


def _logical_cpus(main_results_dir: Path) -> int | None:
    path = main_results_dir / "environment.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("cpu_count_logical")


def _plot_saturation(plt, by_config: dict[str, list[dict]], baseline_ids: list[str], logical_cpus, cfg, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    worker_counts = sorted({row["workers"] for config_id in baseline_ids for row in by_config.get(config_id, [])})
    for config_id in baseline_ids:
        points = sorted((row for row in by_config.get(config_id, []) if not row["skipped"]), key=lambda row: row["workers"])
        if not points:
            continue
        algorithm = points[0]["algorithm"]
        xs = [row["workers"] for row in points]
        style = {"marker": "o", "color": COLORS[algorithm], "linewidth": 2, "label": display_name(algorithm)}
        axes[0].plot(xs, [row["throughput_per_second"] for row in points], **style)
        axes[1].plot(xs, [row["p95_ms"] for row in points], **style)
    for axis in axes:
        if logical_cpus:
            axis.axvline(logical_cpus, color="#666666", linestyle=":", linewidth=1, label=f"{logical_cpus} logical CPUs")
        axis.set_xscale("log", base=2)
        axis.set_xticks(worker_counts, [str(count) for count in worker_counts])
        axis.minorticks_off()
        axis.set_xlabel("Concurrent workers (thread pool)")
        axis.yaxis.grid(True, linestyle="--", alpha=0.4)
        axis.set_axisbelow(True)
    axes[1].axhline(cfg.budget_a_ms, color="#666666", linestyle="--", linewidth=1, label="Budget A")
    axes[0].set_ylabel("Verifications per second")
    axes[1].set_ylabel("p95 verification latency (ms)")
    axes[0].set_title("Supplementary: baseline throughput")
    axes[1].set_title("Supplementary: baseline p95 latency")
    axes[0].legend(fontsize=9)
    axes[1].legend(fontsize=9)
    _save(plt, fig, path)


def _plot_equal_memory(plt, rows: list[dict], targets: list[float], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.4))
    algorithms = [name for name in WRONG_PASSWORD_ALGORITHMS if any(row["algorithm"] == name for row in rows)]
    width = 0.8 / max(1, len(targets))
    hatches = ["", "//", "xx", ".."]
    for target_index, target in enumerate(targets):
        values = []
        for algorithm in algorithms:
            row = next((item for item in rows if item["algorithm"] == algorithm and item["target_ms"] == target), None)
            values.append(0 if row is None or row.get("median_rss_delta_mib") is None else row["median_rss_delta_mib"])
        positions = [index - 0.4 + width * (target_index + 0.5) for index in range(len(algorithms))]
        ax.bar(
            positions,
            values,
            width * 0.92,
            color=[COLORS[name] for name in algorithms],
            hatch=hatches[target_index % len(hatches)],
            edgecolor="#333333",
            linewidth=0.6,
            label=f"Target {target:g} ms",
        )
    ax.set_xticks(range(len(algorithms)), [display_name(name) for name in algorithms])
    ax.set_ylabel("Measured peak memory growth (MiB)")
    ax.set_title("Supplementary: memory used at equal verification time")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9)
    _save(plt, fig, path)


def _wrong_password_table(rows: list[dict], statistics: dict, margin: float) -> list[dict]:
    table = []
    for algorithm in WRONG_PASSWORD_ALGORITHMS:
        group = [row for row in rows if row["algorithm"] == algorithm]
        correct = [row["wall_ns"] / 1e6 for row in group if row["kind"] == "correct"]
        wrong = [row["wall_ns"] / 1e6 for row in group if row["kind"] == "wrong"]
        if not correct or not wrong:
            continue
        low, high = bootstrap_median_contrast_ci(
            wrong,
            correct,
            int(statistics["bootstrap_resamples"]),
            float(statistics["confidence"]),
            _seed_for(int(statistics["seed"]), f"wrong/{algorithm}"),
            ratio=False,
        )
        correct_median = median(correct)
        tested = mann_whitney(wrong, correct)
        limit = margin * correct_median
        table.append(
            {
                "algorithm": algorithm,
                "config_id": group[0]["config_id"],
                "n_correct": len(correct),
                "n_wrong": len(wrong),
                "correct_median_ms": correct_median,
                "wrong_median_ms": median(wrong),
                "difference_ms": median(wrong) - correct_median,
                "difference_ci_low": low,
                "difference_ci_high": high,
                "margin_ms": limit,
                "equivalent": -limit <= low and high <= limit,
                "p_value": tested["p_value"],
                "cliffs_delta": tested["cliffs_delta"],
                "cliffs_magnitude": cliffs_magnitude(tested["cliffs_delta"]),
            }
        )
    return table


def _equal_latency_rows(latency_rows: list[dict], memory_rows: list[dict], statistics: dict) -> list[dict]:
    table = _latency_table(latency_rows)
    _attach_memory(table, _memory_index(memory_rows))
    _attach_intervals(table, statistics)
    for row in table:
        row["target_ms"] = float(row["tags"]["target_ms"])
        row["deviation"] = row["median_ms"] / row["target_ms"] - 1.0
    table.sort(key=lambda row: (row["target_ms"], ALGORITHM_ORDER.get(row["algorithm"], 99)))
    return table


def _input_lines(records: list[dict]) -> list[str]:
    if not records:
        return ["The input-handling experiment has not been collected."]
    names = list(dict.fromkeys(record["name"] for record in records))

    def cell(record: dict | None) -> str:
        if record is None:
            return ""
        if record.get("error"):
            return "rejected"
        return "same key" if record["same_result"] else "different"

    lines = [
        "Each pair was derived with the same salt and the baseline parameters. \"same key\" means both inputs would verify against one stored hash.",
        "",
        _md_table(
            ["Algorithm"] + names,
            [
                [display_name(algorithm)]
                + [cell(next((r for r in records if r["algorithm"] == algorithm and r["name"] == name), None)) for name in names]
                for algorithm in WRONG_PASSWORD_ALGORITHMS
                if any(r["algorithm"] == algorithm for r in records)
            ],
        ),
        "",
    ]
    colliding = sorted(
        {display_name(r["algorithm"]) for r in records if r.get("same_result") is True},
        key=lambda name: name.lower(),
    )
    if colliding:
        lines.append(
            "Pairs that derived the same key: "
            + "; ".join(
                f"{display_name(r['algorithm'])} {r['name']}" for r in records if r.get("same_result") is True
            )
            + "."
        )
        lines.append(
            "HMAC replaces a key longer than the 64-byte SHA-256 block with its digest and pads a shorter key with zero bytes. "
            "PBKDF2-HMAC-SHA256 uses the password as that key, and scrypt applies PBKDF2-HMAC-SHA256 to the password (RFC 7914). "
            "These are distinct byte strings that verify as the same password. They are not a weakness in guessing resistance, "
            "but an application that accepts raw bytes should normalize and bound passwords before hashing."
        )
    rejected = [r for r in records if r.get("error")]
    for record in rejected:
        lines.append(f"{display_name(record['algorithm'])} {record['name']}: {record['error']}.")
    lines.append("This experiment records input handling only. It does not test password guessing.")
    return lines


def run_analyze_supplementary(supp, main_raw_dir: Path, main_results_dir: Path, raw_dir: Path, results_dir: Path, design: str, main_design: str) -> int:
    statistics = _statistics(supp)
    confidence_text = f"{supp.confidence:.0%}"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures = results_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    main_latency_rows = read_jsonl(main_raw_dir / "latency.jsonl")
    main_memory_rows = read_jsonl(main_raw_dir / "memory.jsonl")
    main_concurrent_rows = read_jsonl(main_raw_dir / "concurrent.jsonl")
    files = {
        name: read_jsonl(raw_dir / name)
        for name in (
            "latency.jsonl",
            "memory.jsonl",
            "concurrent.jsonl",
            "concurrent_memory.jsonl",
            "concurrent_extra.jsonl",
            "equal_latency.jsonl",
            "equal_latency_memory.jsonl",
            "equal_latency_calibration.jsonl",
            "wrong_password.jsonl",
            "input_handling.jsonl",
        )
    }
    errors = read_jsonl(raw_dir / "errors.jsonl")
    for filename, rows in (("latency.jsonl", main_latency_rows), ("concurrent.jsonl", main_concurrent_rows)):
        _check_design(rows, main_design, filename)
    for filename, rows in files.items():
        _check_design(rows, design, f"supplementary/{filename}")

    main_latency = _latency_table(main_latency_rows)
    _attach_memory(main_latency, _memory_index(main_memory_rows))
    main_baselines = [row for row in main_latency if "baseline" in row["roles"]]
    extension = _latency_table(files["latency.jsonl"])
    _attach_memory(extension, _memory_index(files["memory.jsonl"]))
    _attach_intervals(extension, statistics)
    extension.sort(key=lambda row: (ALGORITHM_ORDER.get(row["algorithm"], 99), row["parameter_value"]))
    scrypt_rows = [row for row in extension if row["algorithm"] == "scrypt"]
    time_cost_rows = [row for row in extension if row["algorithm"] == "argon2id"]
    scrypt_baseline = [row for row in scrypt_rows if "baseline" in row["roles"]]
    four_baselines = main_baselines + scrypt_baseline
    _attach_intervals(main_baselines, statistics)
    omnibus, pairs = _baseline_tests(four_baselines, statistics)

    concurrent = _concurrent_table(main_concurrent_rows) + _concurrent_table(files["concurrent_extra.jsonl"])
    scrypt_concurrent = _concurrent_table(files["concurrent.jsonl"])
    thread_rows = [row for row in concurrent + scrypt_concurrent if row["pool"] == "thread"]
    by_config: dict[str, list[dict]] = {}
    for row in thread_rows:
        by_config.setdefault(row["config_id"], []).append(row)
    scrypt_memory = _concurrent_memory_index(files["concurrent_memory.jsonl"])
    equal = _equal_latency_rows(files["equal_latency.jsonl"], files["equal_latency_memory.jsonl"], statistics)
    wrong = _wrong_password_table(files["wrong_password.jsonl"], statistics, float(supp.wrong_password["equivalence_margin"]))
    cfg = supp.main

    sweep_columns = [
        "algorithm", "config_id", "parameter_name", "parameter_value", "n", "median_ms", "median_ci_low", "median_ci_high",
        "p95_ms", "p95_ci_low", "p95_ci_high", "median_cpu_ms", "configured_memory_mib", "median_rss_delta_mib", "reduced_sample",
    ]
    _write_csv(results_dir / "s1_scrypt.csv", scrypt_rows, sweep_columns)
    _write_csv(results_dir / "s2_argon2id_time_cost.csv", time_cost_rows, sweep_columns)
    _write_csv(
        results_dir / "s1_four_baseline_statistics.csv",
        pairs,
        ["first", "second", "median_ratio", "median_ratio_ci_low", "median_ratio_ci_high", "mann_whitney_u", "p_value", "p_holm", "cliffs_delta", "cliffs_magnitude"],
    )
    _write_csv(
        results_dir / "s4_concurrency_all_workers.csv",
        sorted(thread_rows + [row for row in scrypt_concurrent if row["pool"] == "process"], key=lambda row: (row["config_id"], row["pool"], row["workers"])),
        ["algorithm", "config_id", "pool", "workers", "skipped", "n", "median_ms", "p95_ms", "throughput_per_second", "cpu_seconds", "pool_startup_ms"],
    )
    _write_csv(results_dir / "s5_equal_latency.csv", equal, ["target_ms"] + sweep_columns + ["deviation"])
    _write_csv(
        results_dir / "s5_equal_latency_calibration.csv",
        files["equal_latency_calibration.jsonl"],
        ["target_ms", "algorithm", "parameter_name", "parameter_value", "step", "median_ms", "chosen"],
    )
    _write_csv(
        results_dir / "s6_wrong_password.csv",
        wrong,
        ["algorithm", "config_id", "n_correct", "n_wrong", "correct_median_ms", "wrong_median_ms", "difference_ms", "difference_ci_low",
         "difference_ci_high", "margin_ms", "equivalent", "p_value", "cliffs_delta", "cliffs_magnitude"],
    )
    _write_csv(
        results_dir / "s7_input_handling.csv",
        files["input_handling.jsonl"],
        ["algorithm", "name", "password_bytes", "alternate_bytes", "same_result", "error", "library", "description"],
    )

    plt = _style()
    if len(scrypt_rows) > 1:
        _plot_rq2(plt, [row for row in scrypt_rows if "sweep" in row["roles"]], figures / "s1_scrypt.png", "Supplementary: ")
    if len(time_cost_rows) > 1:
        _plot_rq2(plt, [row for row in time_cost_rows if "sweep" in row["roles"]], figures / "s2_argon2id_time_cost.png", "Supplementary: ")
    baseline_ids = [row["config_id"] for row in four_baselines]
    if any(by_config.get(config_id) for config_id in baseline_ids):
        _plot_saturation(plt, by_config, baseline_ids, _logical_cpus(main_results_dir), cfg, figures / "s4_saturation.png")
    targets = [float(value) for value in supp.equal_latency["targets_ms"]]
    if equal:
        _plot_equal_memory(plt, equal, targets, figures / "s5_equal_latency_memory.png")

    lines = ["# Supplementary results", ""]
    if design == "smoke":
        lines.extend(["This is a pipeline check. Do not use these numbers in the report.", ""])
    lines.extend(
        [
            "These experiments were declared in config/supplementary.yaml after the proposal and after the first registered runs "
            f"were inspected (SHA-256 {supp.sha256}). They extend the registered experiment. The answers to the three research "
            "questions, and budgets A and B, are in results/summary.md and are not changed here.",
            "",
            "Machine, library versions, and the registered rules are in results/summary.md and results/environment.json. "
            "Every measurement below comes from the same run and machine.",
            "",
        ]
    )

    lines.extend(["## S1. scrypt as a fourth algorithm", ""])
    if four_baselines and scrypt_baseline:
        params = supp.extension.algorithms["scrypt"]["baseline"]
        configured = 128 * int(params["n"]) * int(params["r"]) / MIB
        lines.append(
            "scrypt (hashlib.scrypt, OpenSSL) was added after the proposal. Its baseline follows the OWASP minimum: "
            f"N={params['n']}, r={params['r']}, p={params['p']}, which configures {configured:g} MiB. "
            "The other rows are the registered baselines from the same run."
        )
        lines.append("")
        lines.append(_baseline_table(four_baselines, confidence_text))
        lines.append("")
        lines.extend(_test_lines(omnibus, pairs, confidence_text))
        lines.append("")
        sweep = [row for row in scrypt_rows if "sweep" in row["roles"]]
        if len(sweep) > 1:
            lines.extend(_sweep_lines(sweep))
            lines.append("")
        scrypt_budget = _budget_rows(scrypt_concurrent, supp.extension)
        if scrypt_budget:
            workers = cfg.reference_workers
            lines.append(f"Concurrent verification at {workers} thread-pool workers, judged by the registered budgets:")
            lines.append("")
            lines.append(
                _md_table(
                    ["Configuration", "p95 ms", "Per second", f"Memory MiB, {workers} at once", f"Configured MiB x {workers}", "Budget A", "Budget B"],
                    [
                        [
                            row["config_id"],
                            _fmt(row["p95_ms"]),
                            _fmt(row["throughput_per_second"], 1),
                            _fmt(scrypt_memory.get((row["config_id"], workers), {}).get("fresh_peak_delta_mib"), 1),
                            _fmt(scrypt_memory.get((row["config_id"], workers), {}).get("configured_total_mib"), 1),
                            "yes" if row["meets_a"] else "no",
                            "yes" if row["meets_b"] else "no",
                        ]
                        for row in scrypt_budget
                        if row["measured"]
                    ],
                )
            )
            lines.append("")
            lines.extend(_process_pool_lines(scrypt_concurrent, supp.extension))
    else:
        lines.append("The scrypt measurements have not been collected.")
    lines.append("")

    lines.extend(["## S2. Argon2id time cost", ""])
    sweep = [row for row in time_cost_rows if "sweep" in row["roles"]]
    if len(sweep) > 1:
        fixed = supp.extension.algorithms["argon2id"]["sweep"]["fixed"]
        lines.append(
            f"Memory stays at {_param_text('memory_kib', fixed['memory_kib'])} and parallelism at {fixed['parallelism']}. Only t changes."
        )
        lines.append("")
        lines.extend(_sweep_lines(sweep))
        lines.append("")
        lines.append(
            _md_table(
                ["t", "Median ms", f"{confidence_text} CI", "p95 ms", "CPU ms", "RSS delta MiB", "n"],
                [
                    [
                        str(row["parameter_value"]),
                        _fmt(row["median_ms"]),
                        _ci_text(row, "median_ci_low", "median_ci_high"),
                        _fmt(row["p95_ms"]),
                        _fmt(row["median_cpu_ms"]),
                        _fmt(row.get("median_rss_delta_mib"), 1),
                        str(row["n"]),
                    ]
                    for row in sweep
                ],
            )
        )
    else:
        lines.append("The time-cost sweep has not been collected.")
    lines.append("")

    lines.extend(["## S3. Tighter latency budgets", ""])
    reference = [
        row
        for row in thread_rows
        if row["workers"] == cfg.reference_workers and not row["skipped"] and row["p95_ms"] is not None
    ]
    reference.sort(key=lambda row: (ALGORITHM_ORDER.get(row["algorithm"], 99), row["parameter_value"]))
    if reference:
        budgets = supp.tight_budgets_ms
        lines.append(
            f"Same reference load ({cfg.reference_workers} workers) and throughput minimum ({cfg.throughput_min:g}/s) as the registered "
            f"budgets, with p95 limits of {', '.join(f'{value:g} ms' for value in budgets)}. These limits are supplementary. "
            "The registered budgets A and B still answer research question 3."
        )
        lines.append("")
        for budget in budgets:
            inside = [row["config_id"] for row in reference if meets_budget(row["p95_ms"], row["throughput_per_second"], budget, cfg.throughput_min)]
            lines.append(f"Inside {budget:g} ms: " + (", ".join(inside) if inside else "none") + f" ({len(inside)} of {len(reference)}).")
        lines.append("")
        lines.append(
            _md_table(
                ["Configuration", "p95 ms", "Per second"] + [f"{value:g} ms" for value in budgets],
                [
                    [row["config_id"], _fmt(row["p95_ms"]), _fmt(row["throughput_per_second"], 1)]
                    + ["yes" if meets_budget(row["p95_ms"], row["throughput_per_second"], value, cfg.throughput_min) else "no" for value in budgets]
                    for row in reference
                ],
            )
        )
    else:
        lines.append("Concurrent measurements have not been collected.")
    lines.append("")

    lines.extend(["## S4. Concurrency beyond the core count", ""])
    if by_config:
        logical = _logical_cpus(main_results_dir)
        worker_counts = sorted({row["workers"] for row in thread_rows})
        lines.append(
            f"Thread-pool throughput at {', '.join(str(count) for count in worker_counts)} workers. "
            f"The registered counts come from the registered phase and {', '.join(str(count) for count in supp.extra_workers)} "
            "from the supplementary phase of the same run."
            + (f" This machine reports {logical} logical CPUs." if logical else "")
        )
        lines.append(
            f"The saturation point is the first worker count at which throughput rises by less than {supp.saturation_gain:.0%} "
            f"over the previous count, or p95 exceeds {supp.p95_growth_limit:g} times the 1-worker p95."
        )
        lines.append("")
        ordered_ids = sorted(by_config, key=lambda config_id: (ALGORITHM_ORDER.get(by_config[config_id][0]["algorithm"], 99), by_config[config_id][0]["parameter_value"]))
        table_rows = []
        for config_id in ordered_ids:
            points = {row["workers"]: row for row in by_config[config_id]}
            found = saturation_point(by_config[config_id], supp.saturation_gain, supp.p95_growth_limit)
            cells = [config_id]
            for count in worker_counts:
                row = points.get(count)
                if row is None:
                    cells.append("")
                elif row["skipped"]:
                    cells.append("skipped")
                else:
                    cells.append(f"{row['throughput_per_second']:.1f}")
            cells.append("not reached" if found is None else str(found[0]))
            table_rows.append(cells)
        lines.append(_md_table(["Configuration"] + [f"{count} w/s" for count in worker_counts] + ["Saturation"], table_rows))
        lines.append("")
        lines.append("Values are verifications per second. Per-worker p95 values are in s4_concurrency_all_workers.csv.")
        for config_id in ordered_ids:
            found = saturation_point(by_config[config_id], supp.saturation_gain, supp.p95_growth_limit)
            if found is not None and config_id in baseline_ids:
                lines.append(f"{config_id} saturates at {found[0]} workers: {found[1]}.")
    else:
        lines.append("Concurrent measurements have not been collected.")
    lines.append("")

    lines.extend(["## S5. Equal verification time", ""])
    if equal:
        lines.append(
            "Each algorithm was calibrated to the same target median verification time, then measured with the registered "
            f"warmup and pilot rules and {supp.equal_latency['measured_repeats']} repeats per password. bcrypt cost and scrypt N "
            "double the work per step, so those two use the nearest achievable step and can miss the target. "
            "The deviation column shows by how much."
        )
        lines.append("")
        lines.append(
            _md_table(
                ["Target ms", "Algorithm", "Parameter", "Median ms", f"{confidence_text} CI", "Deviation", "p95 ms", "CPU ms", "RSS delta MiB", "Configured MiB"],
                [
                    [
                        f"{row['target_ms']:g}",
                        display_name(row["algorithm"]),
                        f"{row['parameter_name']} = {_param_text(row['parameter_name'], row['parameter_value'])}",
                        _fmt(row["median_ms"]),
                        _ci_text(row, "median_ci_low", "median_ci_high"),
                        f"{row['deviation']:+.1%}",
                        _fmt(row["p95_ms"]),
                        _fmt(row["median_cpu_ms"]),
                        _fmt(row.get("median_rss_delta_mib"), 1),
                        _fmt(row.get("configured_memory_mib"), 1),
                    ]
                    for row in equal
                ],
            )
        )
        lines.append("")
        for target in targets:
            at_target = [row for row in equal if row["target_ms"] == target]
            memory_text = "; ".join(
                f"{display_name(row['algorithm'])} {row['median_rss_delta_mib']:.1f} MiB"
                for row in at_target
                if row.get("median_rss_delta_mib") is not None
            )
            if memory_text:
                lines.append(f"At about {target:g} ms per verification, measured peak memory growth was {memory_text}.")
        lines.append(
            "Equal time on this CPU does not mean equal cost for an attacker. Memory-hard algorithms also make each parallel guess "
            "hold memory, and this benchmark does not measure attacker hardware."
        )
    else:
        lines.append("The equal-latency experiment has not been collected.")
    lines.append("")

    lines.extend(["## S6. Wrong-password verification time", ""])
    if wrong:
        margin = float(supp.wrong_password["equivalence_margin"])
        lines.append(
            "Correct and wrong passwords were verified in a seeded random interleaving at each baseline. The wrong password has the "
            "same length and differs only in its last character. The difference is the wrong-password median minus the correct-password "
            f"median. The two are called equivalent when its {confidence_text} bootstrap interval lies within +/-{margin:.0%} of the correct median."
        )
        lines.append("")
        lines.append(
            _md_table(
                ["Algorithm", "Correct median ms", "Wrong median ms", "Difference ms", f"{confidence_text} CI", "Equivalent", "Mann-Whitney p", "Cliff's delta"],
                [
                    [
                        display_name(row["algorithm"]),
                        _fmt(row["correct_median_ms"]),
                        _fmt(row["wrong_median_ms"]),
                        f"{row['difference_ms']:+.3f}",
                        f"{row['difference_ci_low']:+.3f} to {row['difference_ci_high']:+.3f}",
                        "yes" if row["equivalent"] else "no",
                        _fmt_p(row["p_value"]),
                        f"{row['cliffs_delta']:+.3f}",
                    ]
                    for row in wrong
                ],
            )
        )
        lines.append("")
        lines.append(
            "Verification derives the full key for any input, so the derivation dominates the time. The PBKDF2 and scrypt wrappers "
            "compare the derived key with hmac.compare_digest; argon2-cffi and bcrypt compare inside the library. Timing at "
            "millisecond scale cannot resolve differences in the final comparison step, so this result does not by itself prove "
            "a constant-time comparison."
        )
    else:
        lines.append("The wrong-password experiment has not been collected.")
    lines.append("")

    lines.extend(["## S7. Input-handling pitfalls", ""])
    lines.extend(_input_lines(files["input_handling.jsonl"]))
    lines.append("See the bcrypt input-length section of results/summary.md for the 72-byte and NUL cases.")
    lines.append("")

    if errors:
        lines.extend(["## Failed configurations", ""])
        for error in errors:
            lines.append(f"- {error.get('experiment')} {error.get('config_id')}: {error.get('error')}")
        lines.append("")
    lines.extend(
        [
            "## Scope",
            "",
            "These are supplementary results for this machine, these library versions, and these configurations. "
            "They are not a universal ranking. The benchmark uses synthetic passwords only and does not perform password cracking.",
            "",
        ]
    )
    (results_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {results_dir / 'summary.md'}", flush=True)
    return 1 if errors else 0
