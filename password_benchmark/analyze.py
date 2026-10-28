"""Build the tables, figures, and summary from raw JSONL measurements."""

import json
import math
import zlib
from pathlib import Path

from password_benchmark.cases import PARAMETER_AXIS, display_name, parameter_axis_value
from password_benchmark.io_utils import read_jsonl
from password_benchmark.stats import (
    bootstrap_median_contrast_ci,
    bootstrap_percentile_ci,
    cliffs_magnitude,
    holm_adjust,
    kruskal_wallis,
    mann_whitney,
    median,
    meets_budget,
    percentile,
)

COLORS = {
    "argon2id": "#0072B2",
    "bcrypt": "#D55E00",
    "pbkdf2_sha256": "#009E73",
    "scrypt": "#CC79A7",
}
MIB = 1024 * 1024
DEFAULT_STATISTICS = {"bootstrap_resamples": 10000, "confidence": 0.95, "seed": 20261028}


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
                "tags": first.get("tags") or {},
                "_walls": walls,
            }
        )
    return table


def _seed_for(base_seed: int, name: str) -> int:
    return base_seed + zlib.crc32(name.encode("utf-8"))


def _attach_intervals(table: list[dict], statistics: dict) -> None:
    """Bootstrap intervals for the median and p95 of each configuration."""
    resamples = int(statistics["bootstrap_resamples"])
    confidence = float(statistics["confidence"])
    for row in table:
        seed = _seed_for(int(statistics["seed"]), row["config_id"])
        row["median_ci_low"], row["median_ci_high"] = bootstrap_percentile_ci(row["_walls"], 50, resamples, confidence, seed)
        row["p95_ci_low"], row["p95_ci_high"] = bootstrap_percentile_ci(row["_walls"], 95, resamples, confidence, seed + 1)


def _fmt_p(value: float) -> str:
    if value < 0.0001:
        return "< 0.0001"
    return f"{value:.4f}"


def _baseline_tests(baselines: list[dict], statistics: dict) -> tuple[dict | None, list[dict]]:
    """Kruskal-Wallis across the baselines, then pairwise Mann-Whitney with Holm adjustment."""
    if len(baselines) < 2:
        return None, []
    omnibus = kruskal_wallis([row["_walls"] for row in baselines]) if len(baselines) > 2 else None
    pairs = []
    for left_index, left in enumerate(baselines):
        for right in baselines[left_index + 1 :]:
            tested = mann_whitney(left["_walls"], right["_walls"])
            low, high = bootstrap_median_contrast_ci(
                left["_walls"],
                right["_walls"],
                int(statistics["bootstrap_resamples"]),
                float(statistics["confidence"]),
                _seed_for(int(statistics["seed"]), left["config_id"] + "/" + right["config_id"]),
                ratio=True,
            )
            pairs.append(
                {
                    "first": left["config_id"],
                    "second": right["config_id"],
                    "first_algorithm": left["algorithm"],
                    "second_algorithm": right["algorithm"],
                    "median_ratio": left["median_ms"] / right["median_ms"],
                    "median_ratio_ci_low": low,
                    "median_ratio_ci_high": high,
                    "mann_whitney_u": tested["u"],
                    "p_value": tested["p_value"],
                    "cliffs_delta": tested["cliffs_delta"],
                    "cliffs_magnitude": cliffs_magnitude(tested["cliffs_delta"]),
                }
            )
    for pair, adjusted in zip(pairs, holm_adjust([pair["p_value"] for pair in pairs])):
        pair["p_holm"] = adjusted
    return omnibus, pairs


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
            "batch_overhead_ms": None,
            "batch_wall_ms": None,
            "config_id": config_id,
            "cpu_seconds": None,
            "median_ms": None,
            "n": 0,
            "p95_ms": None,
            "parameter_name": first["parameter_name"],
            "parameter_value": first["parameter_value"],
            "pool": pool,
            "pool_startup_ms": None,
            "reason": first.get("reason"),
            "roles": first.get("roles") or [],
            "shared_process_peak_rss_mib": None,
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
                    # Wall time not covered by verification work if the workers were always busy.
                    "batch_overhead_ms": batch_wall_s * 1000 - sum(walls) / workers,
                    "batch_wall_ms": batch_wall_s * 1000,
                    "cpu_seconds": first.get("cpu_seconds"),
                    "median_ms": median(walls) if walls else None,
                    "n": len(ok_rows),
                    "p95_ms": percentile(walls, 95) if walls else None,
                    "pool_startup_ms": None if first.get("pool_startup_ns") is None else first["pool_startup_ns"] / 1e6,
                    "shared_process_peak_rss_mib": first["peak_rss"] / MIB,
                    "throughput_per_second": (len(ok_rows) / batch_wall_s) if batch_wall_s else 0.0,
                }
            )
        table.append(item)
    return table


def _concurrent_memory_index(rows: list[dict]) -> dict[tuple, dict]:
    """Fresh-process peak growth while the reference number of verifications run at once."""
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["config_id"], row.get("workers")), []).append(row)
    index = {}
    for key, group in grouped.items():
        measured = [row for row in group if row.get("ok") is True and not row.get("skipped")]
        configured = next((row["configured_memory_bytes"] for row in group if row.get("configured_memory_bytes") is not None), None)
        index[key] = {
            "configured_total_mib": None if configured is None else configured * key[1] / MIB,
            "fresh_peak_delta_mib": median([row["delta_rss"] for row in measured]) / MIB if measured else None,
            "n": len(measured),
            "skipped": not measured,
        }
    return index


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


def _error_bars(rows: list[dict], value: str, low: str, high: str):
    if any(row.get(low) is None for row in rows):
        return None
    return [
        [row[value] - row[low] for row in rows],
        [row[high] - row[value] for row in rows],
    ]


def _plot_rq1(plt, baselines: list[dict], path: Path, title: str = "Baseline verification latency") -> None:
    labels = [display_name(row["algorithm"]) for row in baselines]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    positions = list(range(len(labels)))
    width = 0.36
    error_style = {"capsize": 4, "ecolor": "#333333", "elinewidth": 1}
    ax.bar(
        [p - width / 2 for p in positions],
        [row["median_ms"] for row in baselines],
        width,
        yerr=_error_bars(baselines, "median_ms", "median_ci_low", "median_ci_high"),
        error_kw=error_style,
        label="Median",
        color="#0072B2",
    )
    ax.bar(
        [p + width / 2 for p in positions],
        [row["p95_ms"] for row in baselines],
        width,
        yerr=_error_bars(baselines, "p95_ms", "p95_ci_low", "p95_ci_high"),
        error_kw=error_style,
        label="p95",
        color="#D55E00",
    )
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Verification latency (ms)")
    ax.set_title(title)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(title="Error bars: 95% bootstrap CI", title_fontsize=9)
    _save(plt, fig, path)


def _axis_label(parameter: str) -> str:
    return PARAMETER_AXIS.get(parameter, parameter.replace("_", " "))


def _plot_rq2(plt, rows: list[dict], path: Path, title_prefix: str = "") -> None:
    """Verification time and memory as two panels, so each keeps a single y-axis."""
    ordered = sorted(rows, key=lambda row: row["parameter_value"])
    algorithm = ordered[0]["algorithm"]
    parameter = ordered[0]["parameter_name"]
    name = title_prefix + display_name(algorithm)
    xs = [parameter_axis_value(parameter, row["parameter_value"]) for row in ordered]
    medians = [row["median_ms"] for row in ordered]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    color = COLORS[algorithm]
    axes[0].errorbar(
        xs,
        medians,
        yerr=_error_bars(ordered, "median_ms", "median_ci_low", "median_ci_high"),
        marker="o",
        color=color,
        linewidth=2,
        capsize=3,
        label="Wall time, median (95% CI)",
    )
    cpu = [row["median_cpu_ms"] for row in ordered]
    # Hollow markers keep the wall-time points visible where the two series coincide.
    axes[0].plot(
        xs,
        cpu,
        marker="s",
        markersize=10,
        markerfacecolor="none",
        color="#333333",
        linestyle=":",
        linewidth=1.5,
        label="CPU time, median",
    )
    if all(wall and abs(c / wall - 1.0) < 0.03 for c, wall in zip(cpu, medians)):
        axes[0].text(
            0.97, 0.04, "CPU and wall time coincide (CPU-bound)", transform=axes[0].transAxes, ha="right", fontsize=8, color="#333333"
        )
    for row, x_value, y_value in zip(ordered, xs, medians):
        if row["reduced_sample"]:
            axes[0].annotate("reduced n", (x_value, y_value), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
    axes[0].set_ylabel("Verification time (ms)")
    axes[0].set_title(f"{name}: verification time")
    axes[0].legend(fontsize=9)

    measured = [row.get("median_rss_delta_mib") for row in ordered]
    configured = [row.get("configured_memory_mib") for row in ordered]
    if any(value is not None for value in measured):
        points = [(x_value, value) for x_value, value in zip(xs, measured) if value is not None]
        axes[1].plot(
            [point[0] for point in points],
            [point[1] for point in points],
            marker="o",
            color=color,
            linewidth=2,
            label="Measured peak growth, median",
        )
    if any(value is not None for value in configured):
        axes[1].plot(
            xs,
            configured,
            marker="s",
            markersize=10,
            markerfacecolor="none",
            color="#333333",
            linestyle=":",
            linewidth=1.5,
            label="Configured memory",
        )
    else:
        axes[1].text(
            0.5, 0.9, "No memory-cost parameter", transform=axes[1].transAxes, ha="center", va="top", fontsize=9, color="#555555"
        )
    # Growth of a few MiB is measurement noise; a fixed minimum range keeps it from looking like a trend.
    shown = [value for value in measured + configured if value is not None]
    axes[1].set_ylim(0, max([5.0] + [value * 1.1 for value in shown]))
    axes[1].set_ylabel("Memory during one verification (MiB)")
    axes[1].set_title(f"{name}: memory")
    if axes[1].get_legend_handles_labels()[0]:
        axes[1].legend(fontsize=9, loc="lower right")
    for axis in axes:
        axis.set_xlabel(_axis_label(parameter))
        if parameter == "n":
            axis.set_xscale("log", base=2)
            axis.set_xticks(xs, [f"$2^{{{int(math.log2(x_value))}}}$" for x_value in xs])
            axis.minorticks_off()
        elif parameter in {"cost", "time_cost"}:
            axis.set_xticks(xs, [str(int(x_value)) for x_value in xs])
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


def _p_phrase(value: float) -> str:
    shown = _fmt_p(value)
    return f"p {shown}" if shown.startswith("<") else f"p = {shown}"


def _ci_text(row: dict, low: str, high: str) -> str:
    if row.get(low) is None:
        return ""
    return f"{row[low]:.2f} to {row[high]:.2f}"


def _baseline_table(baselines: list[dict], confidence_text: str) -> str:
    return _md_table(
        ["Algorithm", "Median ms", f"{confidence_text} CI", "p95 ms", f"{confidence_text} CI", "CPU ms", "RSS delta MiB", "Configured MiB", "n"],
        [
            [
                display_name(row["algorithm"]),
                _fmt(row["median_ms"]),
                _ci_text(row, "median_ci_low", "median_ci_high"),
                _fmt(row["p95_ms"]),
                _ci_text(row, "p95_ci_low", "p95_ci_high"),
                _fmt(row["median_cpu_ms"]),
                _fmt(row.get("median_rss_delta_mib"), 1),
                _fmt(row.get("configured_memory_mib"), 1),
                str(row["n"]),
            ]
            for row in baselines
        ],
    )


def _test_lines(omnibus: dict | None, pairs: list[dict], confidence_text: str) -> list[str]:
    if not pairs:
        return []
    lines = ["### Statistical tests", ""]
    if omnibus:
        lines.append(
            f"Kruskal-Wallis across the baselines: H = {omnibus['h']:.1f}, {_p_phrase(omnibus['p_value'])}, "
            f"epsilon-squared = {omnibus['epsilon_squared']:.3f}."
        )
        lines.append("")
    lines.append(
        _md_table(
            ["Comparison", "Median ratio", f"{confidence_text} CI", "Mann-Whitney p (Holm)", "Cliff's delta", "Magnitude"],
            [
                [
                    f"{display_name(pair['first_algorithm'])} / {display_name(pair['second_algorithm'])}",
                    f"{pair['median_ratio']:.3f}",
                    f"{pair['median_ratio_ci_low']:.3f} to {pair['median_ratio_ci_high']:.3f}",
                    _fmt_p(pair["p_holm"]),
                    f"{pair['cliffs_delta']:+.3f}",
                    pair["cliffs_magnitude"],
                ]
                for pair in pairs
            ],
        )
    )
    lines.append("")
    lines.append(
        "The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a "
        "verification of the first algorithm is slower minus the probability that it is faster. With this many verifications "
        "a p-value detects even small differences, so the ratio and Cliff's delta describe the size. "
        "The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift "
        "within a configuration is not modeled."
    )
    return lines


def _sweep_lines(sweep: list[dict]) -> list[str]:
    first, last = sweep[0], sweep[-1]

    def shown(row: dict) -> str:
        interval = _ci_text(row, "median_ci_low", "median_ci_high")
        return f"{row['median_ms']:.2f} ms" + (f" (CI {interval})" if interval else "")

    lines = [
        f"For {display_name(first['algorithm'])}, raising {first['parameter_name']} from "
        f"{_param_text(first['parameter_name'], first['parameter_value'])} to "
        f"{_param_text(last['parameter_name'], last['parameter_value'])} changed median verification latency from "
        f"{shown(first)} to {shown(last)}."
    ]
    reduced = [row for row in sweep if row["reduced_sample"]]
    if reduced:
        listed = ", ".join(row["config_id"] for row in reduced)
        lines.append(f"Reduced samples, because the pilot exceeded the registered threshold: {listed}.")
    return lines


def _process_pool_lines(concurrent: list[dict], cfg) -> list[str]:
    process_rows = [row for row in concurrent if row["pool"] == "process" and not row["skipped"]]
    if not process_rows:
        return ["The process-pool check has not been collected."]
    lines = []
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
            lines.append(f"- {process_row['config_id']}: the thread-pool comparison was not available.")
            continue
        relative = abs(thread_row["throughput_per_second"] - process_row["throughput_per_second"]) / thread_row["throughput_per_second"]
        outside = relative > cfg.process_pool_agreement_ratio
        lines.append(
            f"- {process_row['config_id']}: thread pool {thread_row['throughput_per_second']:.1f}/s, "
            f"process pool {process_row['throughput_per_second']:.1f}/s, relative difference {relative:.1%}, "
            f"{'outside' if outside else 'within'} the registered {cfg.process_pool_agreement_ratio:.0%} agreement range."
        )
        lines.append(
            f"  Per-verification median: thread pool {thread_row['median_ms']:.2f} ms, process pool {process_row['median_ms']:.2f} ms. "
            f"Batch time not explained by verification work (batch wall time minus summed verification time / workers): "
            f"thread pool {thread_row['batch_overhead_ms']:.1f} ms, process pool {process_row['batch_overhead_ms']:.1f} ms "
            f"of {thread_row['batch_wall_ms']:.0f} ms and {process_row['batch_wall_ms']:.0f} ms batches."
        )
        if process_row.get("pool_startup_ms") is None:
            lines.append(
                "  This run was collected before pool workers were started ahead of the clock, so process startup is inside the timed batch."
            )
        else:
            lines.append(
                f"  Worker startup, completed before the clock started and including the warm-up tasks: "
                f"thread pool {thread_row['pool_startup_ms']:.1f} ms, process pool {process_row['pool_startup_ms']:.1f} ms."
            )
        if outside:
            lines.append("  The difference is outside the registered range. It is reported as a finding and the measurement is kept.")
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


def run_analyze(cfg, raw_dir: Path, results_dir: Path, design: str, statistics: dict | None = None) -> int:
    statistics = statistics or DEFAULT_STATISTICS
    confidence_text = f"{float(statistics['confidence']):.0%}"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures = results_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    latency_rows = read_jsonl(raw_dir / "latency.jsonl")
    memory_rows = read_jsonl(raw_dir / "memory.jsonl")
    concurrent_rows = read_jsonl(raw_dir / "concurrent.jsonl")
    concurrent_memory_rows = read_jsonl(raw_dir / "concurrent_memory.jsonl")
    bcrypt_rows = read_jsonl(raw_dir / "bcrypt_length.jsonl")
    errors = read_jsonl(raw_dir / "errors.jsonl")
    for filename, rows in (
        ("latency.jsonl", latency_rows),
        ("memory.jsonl", memory_rows),
        ("concurrent.jsonl", concurrent_rows),
        ("concurrent_memory.jsonl", concurrent_memory_rows),
        ("bcrypt_length.jsonl", bcrypt_rows),
    ):
        _check_design(rows, design, filename)

    latency = _latency_table(latency_rows)
    hashes = _hash_table(latency_rows)
    memory_index = _memory_index(memory_rows)
    _attach_memory(latency, memory_index)
    _attach_intervals(latency, statistics)
    concurrent = _concurrent_table(concurrent_rows)
    concurrent_memory = _concurrent_memory_index(concurrent_memory_rows)
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
        "median_ci_low",
        "median_ci_high",
        "p95_ms",
        "p95_ci_low",
        "p95_ci_high",
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
        "cpu_seconds",
        "batch_wall_ms",
        "batch_overhead_ms",
        "pool_startup_ms",
        "shared_process_peak_rss_mib",
        "parameter_name",
        "parameter_value",
        "reason",
    ]
    _write_csv(results_dir / "rq3_concurrency.csv", concurrent, concurrent_columns)
    _write_csv(
        results_dir / "rq3_concurrent_memory.csv",
        [
            {"config_id": config_id, "workers": workers, **info}
            for (config_id, workers), info in sorted(concurrent_memory.items(), key=lambda item: (str(item[0][0]), item[0][1] or 0))
        ],
        ["config_id", "workers", "n", "skipped", "fresh_peak_delta_mib", "configured_total_mib"],
    )
    omnibus, pairs = _baseline_tests(baselines, statistics)
    _write_csv(
        results_dir / "rq1_statistics.csv",
        pairs,
        [
            "first",
            "second",
            "median_ratio",
            "median_ratio_ci_low",
            "median_ratio_ci_high",
            "mann_whitney_u",
            "p_value",
            "p_holm",
            "cliffs_delta",
            "cliffs_magnitude",
        ],
    )
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
                f"{display_name(row['algorithm'])} {row['median_ms']:.2f} ms "
                f"({confidence_text} CI {row['median_ci_low']:.2f} to {row['median_ci_high']:.2f}; "
                f"p95 {row['p95_ms']:.2f} ms, CPU {row['median_cpu_ms']:.2f} ms)"
                for row in baselines
            )
            + "."
        )
        lines.append("")
        lines.append(_baseline_table(baselines, confidence_text))
        lines.append("")
        lines.extend(_test_lines(omnibus, pairs, confidence_text))
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
        lines.extend(_sweep_lines(sweep))
    if not any("sweep" in row["roles"] for row in latency):
        lines.append("Parameter-sweep measurements have not been collected.")
    else:
        lines.append("")
        lines.append(f"Intervals for every sweep point are in rq2_parameter_sweep.csv ({confidence_text} bootstrap).")
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
        workers = cfg.reference_workers
        lines.append(
            _md_table(
                ["Configuration", "p95 ms", "Per second", f"Memory MiB, {workers} at once", f"Configured MiB x {workers}", "Budget A", "Budget B"],
                [
                    [
                        row["config_id"],
                        _fmt(row["p95_ms"]),
                        _fmt(row["throughput_per_second"], 1),
                        _fmt(concurrent_memory.get((row["config_id"], workers), {}).get("fresh_peak_delta_mib"), 1),
                        _fmt(concurrent_memory.get((row["config_id"], workers), {}).get("configured_total_mib"), 1),
                        "yes" if row["meets_a"] else "no",
                        "yes" if row["meets_b"] else "no",
                    ]
                    for row in budget_rows
                    if row["measured"]
                ],
            )
        )
        lines.append("")
        if concurrent_memory:
            lines.append(
                f"The memory column is the median peak growth of a fresh process while {workers} verifications ran at once "
                f"(rq3_concurrent_memory.csv). It is measured separately from the throughput batches. "
                "The throughput batches reuse one process, so their process-tree RSS (shared_process_peak_rss_mib in "
                "rq3_concurrency.csv) includes memory retained from earlier configurations and is not an isolated measurement."
            )
        else:
            lines.append(
                "This run has no fresh-process concurrent memory measurement, so the memory column is empty. "
                "The process-tree RSS in rq3_concurrency.csv (shared_process_peak_rss_mib) includes memory retained from "
                "earlier configurations and is not an isolated measurement."
            )
        lines.append("")
        lines.append("### Process-pool check")
        lines.append("")
        lines.extend(_process_pool_lines(concurrent, cfg))
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
