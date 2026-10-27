"""Build the tables, figures, and summary from raw JSONL measurements."""

import json
from pathlib import Path

from password_benchmark.cases import display_name, parameter_axis_value
from password_benchmark.io_utils import read_jsonl
from password_benchmark.stats import median, meets_budget, percentile

COLORS = {
    "argon2id": "#0072B2",
    "bcrypt": "#D55E00",
    "pbkdf2_sha256": "#009E73",
}
MIB = 1024 * 1024


def _check_design(rows: list[dict], expected: str, filename: str) -> None:
    found = {row.get("design") for row in rows if row.get("design")}
    if found and found != {expected}:
        raise SystemExit(
            f"{filename} contains design {sorted(found)}, and this command expected {expected}. "
            "Pipeline-check output stays in results/smoke."
        )


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _bcrypt_cell(value, rejected: bool) -> str:
    if rejected and value is None:
        return "rejected"
    if value is None:
        return ""
    return str(value).lower()


def _param_text(name: str, value: int) -> str:
    shown = parameter_axis_value(name, int(value))
    if name == "memory_kib":
        if shown.is_integer():
            return f"{shown:.0f} MiB"
        return f"{shown:.2f} MiB"
    return str(int(value))


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    import pandas as pd

    frame = pd.DataFrame(rows, columns=columns)
    frame.to_csv(path, index=False)


def _latency_table(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("phase") == "measured" and row.get("operation") == "verify" and row.get("ok") is True:
            grouped.setdefault(row["config_id"], []).append(row)
    table = []
    for config_id, group in grouped.items():
        first = group[0]
        walls = [row["wall_ns"] / 1e6 for row in group]
        cpus = [row["cpu_ns"] / 1e6 for row in group]
        table.append(
            {
                "algorithm": first["algorithm"],
                "config_id": config_id,
                "median_cpu_ms": median(cpus),
                "median_ms": median(walls),
                "n": len(group),
                "p95_ms": percentile(walls, 95),
                "parameter_name": first["parameter_name"],
                "parameter_value": first["parameter_value"],
                "pilot_median_ms": first.get("pilot_median_ms"),
                "reduced_sample": bool(first.get("reduced_sample")),
                "repeats_used": first.get("repeats_used"),
                "roles": first["roles"],
            }
        )
    return table


def _hash_table(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("phase") == "hash" and row.get("ok") is True:
            grouped.setdefault(row["config_id"], []).append(row)
    table = []
    for config_id, group in grouped.items():
        first = group[0]
        walls = [row["wall_ns"] / 1e6 for row in group]
        table.append(
            {
                "algorithm": first["algorithm"],
                "config_id": config_id,
                "median_hash_ms": median(walls),
                "n": len(group),
                "parameter_name": first["parameter_name"],
                "parameter_value": first["parameter_value"],
            }
        )
    return table


def _memory_index(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("ok") is True:
            grouped.setdefault(row["config_id"], []).append(row)
    index = {}
    for config_id, group in grouped.items():
        configured = group[0].get("configured_memory_bytes")
        index[config_id] = {
            "configured_memory_mib": None if configured is None else configured / MIB,
            "median_delta_mib": median([row["delta_rss"] for row in group]) / MIB,
            "median_peak_mib": median([row["peak_rss"] for row in group]) / MIB,
            "n_memory": len(group),
        }
    return index


def _attach_memory(table: list[dict], memory_index: dict[str, dict]) -> None:
    for row in table:
        info = memory_index.get(row["config_id"], {})
        row["configured_memory_mib"] = info.get("configured_memory_mib")
        row["median_rss_delta_mib"] = info.get("median_delta_mib")
        row["n_memory"] = info.get("n_memory")


def _concurrent_table(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        skipped = bool(row.get("skipped"))
        key = (row["config_id"], row.get("pool"), row.get("workers"), skipped)
        grouped.setdefault(key, []).append(row)
    table = []
    for (config_id, pool, workers, skipped), group in grouped.items():
        first = group[0]
        item = {
            "algorithm": first["algorithm"],
            "config_id": config_id,
            "cpu_seconds": None,
            "median_ms": None,
            "n": 0,
            "p95_ms": None,
            "parameter_name": first["parameter_name"],
            "parameter_value": first["parameter_value"],
            "peak_rss_mib": None,
            "pool": pool,
            "reason": first.get("reason"),
            "roles": first.get("roles") or [],
            "skipped": skipped,
            "throughput_per_second": None,
            "workers": workers,
        }
        if not skipped:
            ok_rows = [row for row in group if row.get("ok") is True]
            walls = [row["verify_wall_ns"] / 1e6 for row in ok_rows]
            batch_wall_s = first["batch_wall_ns"] / 1e9
            item.update(
                {
                    "cpu_seconds": first.get("cpu_seconds"),
                    "median_ms": median(walls) if walls else None,
                    "n": len(ok_rows),
                    "p95_ms": percentile(walls, 95) if walls else None,
                    "peak_rss_mib": first["peak_rss"] / MIB,
                    "throughput_per_second": (len(ok_rows) / batch_wall_s) if batch_wall_s else 0.0,
                }
            )
        table.append(item)
    return table


def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "font.size": 11,
            "savefig.dpi": 150,
        }
    )
    return plt


def _save(plt, fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_rq1(plt, baselines: list[dict], path: Path) -> None:
    labels = [display_name(row["algorithm"]) for row in baselines]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    positions = list(range(len(labels)))
    width = 0.36
    ax.bar([p - width / 2 for p in positions], [row["median_ms"] for row in baselines], width, label="Median", color="#0072B2")
    ax.bar([p + width / 2 for p in positions], [row["p95_ms"] for row in baselines], width, label="p95", color="#D55E00")
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Verification latency (ms)")
    ax.set_title("Baseline verification latency")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend()
    _save(plt, fig, path)


def _plot_rq2(plt, rows: list[dict], path: Path) -> None:
    ordered = sorted(rows, key=lambda row: row["parameter_value"])
    algorithm = ordered[0]["algorithm"]
    parameter = ordered[0]["parameter_name"]
    xs = [parameter_axis_value(parameter, row["parameter_value"]) for row in ordered]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    color = COLORS[algorithm]
    axes[0].plot(xs, [row["median_ms"] for row in ordered], marker="o", color=color)
    axes[1].plot(xs, [row["median_cpu_ms"] for row in ordered], marker="o", color=color, label="CPU")
    memory = [row.get("median_rss_delta_mib") for row in ordered]
    if any(value is not None for value in memory):
        twin = axes[1].twinx()
        twin.plot(xs, [0 if value is None else value for value in memory], marker="s", color="#000000", label="RSS delta")
        twin.set_ylabel("Median RSS delta (MiB)")
    for row, x_value, y_value in zip(ordered, xs, [row["median_ms"] for row in ordered]):
        if row["reduced_sample"]:
            axes[0].annotate("reduced n", (x_value, y_value), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
    axes[0].set_xlabel(parameter.replace("_", " "))
    axes[1].set_xlabel(parameter.replace("_", " "))
    if parameter == "memory_kib":
        axes[0].set_xlabel("Memory (MiB)")
        axes[1].set_xlabel("Memory (MiB)")
    axes[0].set_ylabel("Median verification latency (ms)")
    axes[1].set_ylabel("Median CPU time (ms)")
    axes[0].set_title(display_name(algorithm))
    axes[1].set_title("CPU and memory")
    for axis in axes:
        axis.yaxis.grid(True, linestyle="--", alpha=0.4)
        axis.set_axisbelow(True)
    _save(plt, fig, path)


def _plot_baseline_concurrency(plt, rows: list[dict], cfg, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for algorithm in cfg.algorithms:
        points = sorted(
            [row for row in rows if row["algorithm"] == algorithm and "baseline" in row["roles"] and not row["skipped"]],
            key=lambda row: row["workers"],
        )
        if not points:
            continue
        xs = [row["workers"] for row in points]
        axes[0].plot(xs, [row["throughput_per_second"] for row in points], marker="o", color=COLORS[algorithm], label=display_name(algorithm))
        axes[1].plot(xs, [row["p95_ms"] for row in points], marker="o", color=COLORS[algorithm], label=display_name(algorithm))
    axes[0].axhline(cfg.throughput_min, color="#666666", linestyle="--", linewidth=1, label="Minimum throughput")
    axes[1].axhline(cfg.budget_a_ms, color="#666666", linestyle="--", linewidth=1, label="Budget A")
    axes[1].axhline(cfg.budget_b_ms, color="#666666", linestyle=":", linewidth=1, label="Budget B")
    axes[0].set_xlabel("Concurrent workers")
    axes[1].set_xlabel("Concurrent workers")
    axes[0].set_ylabel("Verifications per second")
    axes[1].set_ylabel("p95 verification latency (ms)")
    axes[0].set_title("Baseline throughput")
    axes[1].set_title("Baseline p95 latency")
    for axis in axes:
        axis.yaxis.grid(True, linestyle="--", alpha=0.4)
        axis.set_axisbelow(True)
        axis.legend()
    _save(plt, fig, path)


def _plot_reference_load(plt, rows: list[dict], cfg, path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    algorithms = list(cfg.algorithms)
    for column, algorithm in enumerate(algorithms):
        points = sorted(
            [
                row
                for row in rows
                if row["algorithm"] == algorithm and row["workers"] == cfg.reference_workers and not row["skipped"]
            ],
            key=lambda row: row["parameter_value"],
        )
        top = axes[0][column]
        bottom = axes[1][column]
        top.set_title(display_name(algorithm))
        if not points:
            top.text(0.5, 0.5, "not measured", ha="center", va="center")
            bottom.text(0.5, 0.5, "not measured", ha="center", va="center")
            continue
        parameter = points[0]["parameter_name"]
        xs = [parameter_axis_value(parameter, row["parameter_value"]) for row in points]
        xlabel = "Memory (MiB)" if parameter == "memory_kib" else parameter.replace("_", " ")
        top.plot(xs, [row["p95_ms"] for row in points], marker="o", color=COLORS[algorithm])
        bottom.plot(xs, [row["throughput_per_second"] for row in points], marker="o", color=COLORS[algorithm])
        top.axhline(cfg.budget_a_ms, color="#666666", linestyle="--", linewidth=1)
        top.axhline(cfg.budget_b_ms, color="#666666", linestyle=":", linewidth=1)
        bottom.axhline(cfg.throughput_min, color="#666666", linestyle="--", linewidth=1)
        top.set_ylabel("p95 latency (ms)" if column == 0 else "")
        bottom.set_ylabel("Verifications per second" if column == 0 else "")
        bottom.set_xlabel(xlabel)
    _save(plt, fig, path)


def _budget_rows(rows: list[dict], cfg) -> list[dict]:
    selected = []
    for row in rows:
        if row["pool"] != "thread" or row["workers"] != cfg.reference_workers:
            continue
        item = dict(row)
        if row["skipped"] or row["p95_ms"] is None or row["throughput_per_second"] is None:
            item["meets_a"] = False
            item["meets_b"] = False
            item["measured"] = False
        else:
            item["meets_a"] = meets_budget(row["p95_ms"], row["throughput_per_second"], cfg.budget_a_ms, cfg.throughput_min)
            item["meets_b"] = meets_budget(row["p95_ms"], row["throughput_per_second"], cfg.budget_b_ms, cfg.throughput_min)
            item["measured"] = True
        selected.append(item)
    return selected


def _observe_bcrypt(records: list[dict]) -> list[str]:
    by_name = {record["name"]: record for record in records}
    lines = []
    long_rows = [record for record in records if record.get("password_bytes", 0) > 72]
    rejected = [record for record in long_rows if record.get("error")]
    if long_rows and len(rejected) == len(long_rows):
        lines.append(
            "The selected bcrypt library rejected every password longer than 72 bytes before hashing "
            f"({rejected[0]['error']}). It did not silently keep only the first 72 bytes."
        )
    else:
        pair = by_name.get("prefix72_pair")
        if pair and pair.get("alternate_verify") is True:
            lines.append(
                "For this bcrypt library, two passwords that differ only after byte 72 verified against the same hash."
            )
        elif pair and pair.get("alternate_verify") is False:
            lines.append(
                "For this bcrypt library, two passwords that differ only after byte 72 did not verify against the same hash."
            )
        utf8 = by_name.get("utf8_boundary")
        if utf8 and utf8.get("alternate_verify") is not None:
            same = "did" if utf8["alternate_verify"] else "did not"
            lines.append(
                "The UTF-8 pair, whose encoded forms share the first 72 bytes and differ in the final byte, "
                f"{same} verify as the same password."
            )
    nul = by_name.get("nul_inside_first_72")
    if nul and nul.get("error"):
        lines.append(f"The NUL-byte case raised an error: {nul['error']}.")
    elif nul and nul.get("truncated_at_nul_verify") is True:
        lines.append(
            "A password containing a NUL byte matched the shorter password that ends at that NUL, so the library stopped reading at the NUL."
        )
    elif nul and nul.get("truncated_at_nul_verify") is False:
        lines.append(
            "A password containing a NUL byte did not match the shorter prefix that ends at that NUL, so the library kept the bytes after the NUL."
        )
        if nul.get("alternate_verify") is False:
            lines.append("Changing only the bytes after that NUL produced a different verification result.")
    if rejected and long_rows and len(rejected) == len(long_rows):
        lines.append(
            "This library enforces the 72-byte limit by rejecting the input. Application code should still impose the same limit so the user receives a clear validation error. "
            "This experiment records input handling only. It does not test password guessing."
        )
    else:
        lines.append(
            "A deployment that uses this bcrypt library needs an explicit maximum of 72 bytes, and should reject a NUL byte. "
            "This experiment records input handling only. It does not test password guessing."
        )
    return lines


def _environment_lines(results_dir: Path) -> list[str]:
    path = results_dir / "environment.json"
    if not path.exists():
        return ["Machine details were not recorded. Run the environment command before the report is written."]
    env = json.loads(path.read_text(encoding="utf-8"))
    ram_gib = env["ram_bytes"] / (1024 ** 3)
    libraries = ", ".join(f"{name} {version}" for name, version in env["libraries"].items())
    return [
        f"Python: {env['python'].splitlines()[0]}",
        f"OpenSSL: {env['openssl']}",
        f"CPU: {env['cpu_name']} ({env['cpu_count_physical']} physical cores, {env['cpu_count_logical']} logical)",
        f"RAM: {ram_gib:.1f} GiB",
        f"Platform: {env['platform']}",
        f"Power scheme: {env['power_scheme']}",
        f"Libraries: {libraries}",
        f"Config SHA-256: {env['config_sha256']}",
        "The full package list is in environment.json.",
    ]


def run_analyze(cfg, raw_dir: Path, results_dir: Path, design: str) -> int:
    results_dir.mkdir(parents=True, exist_ok=True)
    figures = results_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    latency_rows = read_jsonl(raw_dir / "latency.jsonl")
    memory_rows = read_jsonl(raw_dir / "memory.jsonl")
    concurrent_rows = read_jsonl(raw_dir / "concurrent.jsonl")
    bcrypt_rows = read_jsonl(raw_dir / "bcrypt_length.jsonl")
    errors = read_jsonl(raw_dir / "errors.jsonl")
    for filename, rows in (
        ("latency.jsonl", latency_rows),
        ("memory.jsonl", memory_rows),
        ("concurrent.jsonl", concurrent_rows),
        ("bcrypt_length.jsonl", bcrypt_rows),
    ):
        _check_design(rows, design, filename)

    latency = _latency_table(latency_rows)
    hashes = _hash_table(latency_rows)
    memory_index = _memory_index(memory_rows)
    _attach_memory(latency, memory_index)
    concurrent = _concurrent_table(concurrent_rows)
    order = {name: index for index, name in enumerate(cfg.algorithms)}
    latency.sort(key=lambda row: (order[row["algorithm"]], row["parameter_value"]))
    concurrent.sort(key=lambda row: (order[row["algorithm"]], row["parameter_value"], row["pool"], row["workers"]))

    baselines = [row for row in latency if "baseline" in row["roles"]]
    warnings = []
    if design == "registered":
        for row in latency:
            if row["n"] < 100:
                warnings.append(f"{row['config_id']} has {row['n']} measured verifications. The registered design expects 400 or 1000.")
    for row in latency:
        configured = row.get("configured_memory_mib")
        measured = row.get("median_rss_delta_mib")
        if configured and measured is not None and measured < 0.5 * configured:
            warnings.append(
                f"{row['config_id']} measured an RSS delta of {measured:.1f} MiB, below half of the configured {configured:.1f} MiB. Treat that memory sample as unreliable."
            )

    csv_columns = [
        "algorithm",
        "config_id",
        "parameter_name",
        "parameter_value",
        "n",
        "median_ms",
        "p95_ms",
        "median_cpu_ms",
        "configured_memory_mib",
        "median_rss_delta_mib",
        "reduced_sample",
        "pilot_median_ms",
        "repeats_used",
    ]
    _write_csv(results_dir / "rq1_baseline.csv", baselines, csv_columns)
    _write_csv(results_dir / "rq2_parameter_sweep.csv", [row for row in latency if "sweep" in row["roles"]], csv_columns)
    concurrent_columns = [
        "algorithm",
        "config_id",
        "pool",
        "workers",
        "skipped",
        "n",
        "median_ms",
        "p95_ms",
        "throughput_per_second",
        "peak_rss_mib",
        "cpu_seconds",
        "parameter_name",
        "parameter_value",
        "reason",
    ]
    _write_csv(results_dir / "rq3_concurrency.csv", concurrent, concurrent_columns)
    _write_csv(
        results_dir / "bcrypt_length.csv",
        bcrypt_rows,
        [
            "name",
            "password_bytes",
            "alternate_bytes",
            "self_verify",
            "prefix72_verify",
            "alternate_verify",
            "truncated_at_nul_verify",
            "cost",
            "library_version",
            "error",
            "description",
        ],
    )
    _write_csv(results_dir / "appendix_hash_time.csv", hashes, ["algorithm", "config_id", "parameter_name", "parameter_value", "n", "median_hash_ms"])

    if latency or concurrent:
        plt = _style()
        if baselines:
            _plot_rq1(plt, baselines, figures / "rq1_baseline.png")
        for algorithm in cfg.algorithms:
            sweep = [row for row in latency if row["algorithm"] == algorithm and "sweep" in row["roles"]]
            if sweep:
                _plot_rq2(plt, sweep, figures / f"rq2_{algorithm}.png")
        thread_rows = [row for row in concurrent if row["pool"] == "thread"]
        if any(not row["skipped"] and "baseline" in row["roles"] for row in thread_rows):
            _plot_baseline_concurrency(plt, thread_rows, cfg, figures / "rq3_baseline_concurrency.png")
        if any(not row["skipped"] and row["workers"] == cfg.reference_workers for row in thread_rows):
            _plot_reference_load(plt, thread_rows, cfg, figures / "rq3_reference_load.png")

    lines = ["# Results summary", ""]
    if design == "smoke":
        lines.extend(["This is a pipeline check. Do not use these numbers in the report.", ""])
    lines.extend(["## Machine", ""] + [f"- {line}" for line in _environment_lines(results_dir)] + [""])
    lines.extend(
        [
            "## Registered rules",
            "",
            (
                f"Warmup verifications discarded per configuration: {cfg.warmup_repeats}. "
                f"Pilot verifications: {cfg.pilot_repeats}. "
                f"Measured repeats per password: {cfg.measured_repeats}, "
                f"or {cfg.slow_repeats} when the pilot median exceeds {cfg.slow_threshold_ms:.0f} ms."
            ),
            (
                f"Budget A requires p95 latency at or below {cfg.budget_a_ms:.0f} ms and throughput of at least "
                f"{cfg.throughput_min:.0f} verifications per second at {cfg.reference_workers} concurrent workers. "
                f"Budget B uses the same throughput rule and a p95 limit of {cfg.budget_b_ms:.0f} ms. "
                "Both conditions are required."
            ),
            "Verification time excludes salt generation and hash construction. Those happen before the timed calls.",
            "Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.",
            "",
        ]
    )

    lines.extend(["## Research question 1", ""])
    if baselines:
        lines.append(
            "Under the baseline configurations, median verification latency was "
            + "; ".join(
                f"{display_name(row['algorithm'])} {row['median_ms']:.2f} ms (p95 {row['p95_ms']:.2f} ms, CPU {row['median_cpu_ms']:.2f} ms)"
                for row in baselines
            )
            + "."
        )
        lines.append("")
        lines.append(
            _md_table(
                ["Algorithm", "Median ms", "p95 ms", "CPU ms", "RSS delta MiB", "Configured MiB", "n"],
                [
                    [
                        display_name(row["algorithm"]),
                        _fmt(row["median_ms"]),
                        _fmt(row["p95_ms"]),
                        _fmt(row["median_cpu_ms"]),
                        _fmt(row.get("median_rss_delta_mib"), 1),
                        _fmt(row.get("configured_memory_mib"), 1),
                        str(row["n"]),
                    ]
                    for row in baselines
                ],
            )
        )
    else:
        lines.append("Latency measurements have not been collected.")
    lines.append("")

    lines.extend(["## Research question 2", ""])
    for algorithm in cfg.algorithms:
        sweep = sorted(
            [row for row in latency if row["algorithm"] == algorithm and "sweep" in row["roles"]],
            key=lambda row: row["parameter_value"],
        )
        if len(sweep) < 2:
            continue
        first, last = sweep[0], sweep[-1]
        lines.append(
            f"For {display_name(algorithm)}, raising {first['parameter_name']} from "
            f"{_param_text(first['parameter_name'], first['parameter_value'])} to "
            f"{_param_text(last['parameter_name'], last['parameter_value'])} changed median verification latency from "
            f"{first['median_ms']:.2f} ms to {last['median_ms']:.2f} ms."
        )
        reduced = [row for row in sweep if row["reduced_sample"]]
        if reduced:
            listed = ", ".join(row["config_id"] for row in reduced)
            lines.append(f"Reduced samples, because the pilot exceeded the registered threshold: {listed}.")
    if not any("sweep" in row["roles"] for row in latency):
        lines.append("Parameter-sweep measurements have not been collected.")
    lines.append("")

    lines.extend(["## Research question 3", ""])
    budget_rows = _budget_rows(concurrent, cfg)
    if budget_rows:
        measured_rows = [row for row in budget_rows if row["measured"]]
        met_a = [row["config_id"] for row in measured_rows if row["meets_a"]]
        met_b_only = [row["config_id"] for row in measured_rows if row["meets_b"] and not row["meets_a"]]
        neither = [row["config_id"] for row in measured_rows if not row["meets_b"]]
        missing = [row["config_id"] for row in budget_rows if not row["measured"]]
        lines.append(
            f"At {cfg.reference_workers} concurrent thread-pool verifications, configurations inside budget A: "
            + (", ".join(met_a) if met_a else "none")
            + "."
        )
        lines.append("Inside budget B but outside budget A: " + (", ".join(met_b_only) if met_b_only else "none") + ".")
        lines.append("Outside both budgets: " + (", ".join(neither) if neither else "none") + ".")
        if missing:
            lines.append("Not measured at the reference load: " + ", ".join(missing) + ".")
        lines.append("")
        lines.append(
            _md_table(
                ["Configuration", "p95 ms", "Per second", "Peak RSS MiB", "Budget A", "Budget B"],
                [
                    [
                        row["config_id"],
                        _fmt(row["p95_ms"]),
                        _fmt(row["throughput_per_second"], 1),
                        _fmt(row["peak_rss_mib"], 1),
                        "yes" if row["meets_a"] else "no",
                        "yes" if row["meets_b"] else "no",
                    ]
                    for row in budget_rows
                    if row["measured"]
                ],
            )
        )
        lines.append("")
        lines.append("### Process-pool check")
        lines.append("")
        process_rows = [row for row in concurrent if row["pool"] == "process" and not row["skipped"]]
        if not process_rows:
            lines.append("The process-pool check has not been collected.")
        for process_row in process_rows:
            thread_row = next(
                (
                    row
                    for row in concurrent
                    if row["pool"] == "thread"
                    and row["config_id"] == process_row["config_id"]
                    and row["workers"] == process_row["workers"]
                    and not row["skipped"]
                ),
                None,
            )
            if thread_row is None or not thread_row["throughput_per_second"] or process_row["throughput_per_second"] is None:
                lines.append(f"{process_row['config_id']}: the thread-pool comparison was not available.")
                continue
            relative = abs(thread_row["throughput_per_second"] - process_row["throughput_per_second"]) / thread_row["throughput_per_second"]
            relation = "within" if relative <= cfg.process_pool_agreement_ratio else "outside"
            lines.append(
                f"{process_row['config_id']}: thread pool {thread_row['throughput_per_second']:.1f}/s, "
                f"process pool {process_row['throughput_per_second']:.1f}/s, relative difference {relative:.1%}, "
                f"{relation} the registered {cfg.process_pool_agreement_ratio:.0%} agreement range."
            )
    else:
        lines.append("Concurrent measurements have not been collected.")
    lines.append("")

    lines.extend(["## bcrypt input length", ""])
    if bcrypt_rows:
        version = bcrypt_rows[0].get("library_version", "")
        cost = bcrypt_rows[0].get("cost", "")
        lines.append(f"Library bcrypt {version}, cost {cost}.")
        lines.append("")
        lines.extend(_observe_bcrypt(bcrypt_rows))
        lines.append("")
        lines.append(
            _md_table(
                ["Case", "Bytes", "Self", "First 72 bytes", "Alternate", "Stops at NUL"],
                [
                    [
                        row["name"],
                        str(row["password_bytes"]),
                        _bcrypt_cell(row["self_verify"], bool(row.get("error"))),
                        _bcrypt_cell(row["prefix72_verify"], bool(row.get("error"))),
                        _bcrypt_cell(row["alternate_verify"], bool(row.get("error"))),
                        _bcrypt_cell(row["truncated_at_nul_verify"], bool(row.get("error"))),
                    ]
                    for row in bcrypt_rows
                ],
            )
        )
    else:
        lines.append("The bcrypt length experiment has not been collected.")
    lines.append("")

    lines.extend(["## Appendix: hash construction", ""])
    lines.append("These times are not part of the verification comparison. Hash construction was excluded from the timed verification calls.")
    lines.append("")
    if hashes:
        hashes.sort(key=lambda row: (order.get(row["algorithm"], 0), row["parameter_value"]))
        lines.append(
            _md_table(
                ["Configuration", "Median hash ms", "n"],
                [[row["config_id"], _fmt(row["median_hash_ms"]), str(row["n"])] for row in hashes],
            )
        )
    else:
        lines.append("Hash-construction times have not been collected.")
    lines.append("")

    if warnings:
        lines.extend(["## Warnings", ""] + [f"- {warning}" for warning in warnings] + [""])
    if errors:
        lines.extend(["## Failed configurations", ""])
        for error in errors:
            lines.append(f"- {error.get('experiment')} {error.get('config_id')}: {error.get('error')}")
        lines.append("")
        lines.append("Tracebacks are stored in data/raw/errors.jsonl or the matching smoke file.")
        lines.append("")

    lines.extend(
        [
            "## Scope",
            "",
            "These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.",
            "The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.",
            "",
        ]
    )
    (results_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {results_dir / 'summary.md'}", flush=True)
    return 1 if errors else 0
