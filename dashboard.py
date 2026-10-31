"""Presentation dashboard for the saved benchmark runs.

    streamlit run dashboard.py

It only reads files that the benchmark already wrote under runs/ (and, for the
optional web login test, results/supplementary/). Nothing here changes a run.
The live demonstration page times a few verifications on the presenting
machine; those numbers are not experimental results.
"""

import json
import statistics
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from password_benchmark.analyze import COLORS, _latency_table, _param_text
from password_benchmark.cases import display_name
from password_benchmark.config import load_config
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import read_jsonl
from password_benchmark.paths import ROOT
from password_benchmark.stats import kruskal_wallis
from password_benchmark.supplementary import load_supplementary

ALGORITHMS = ["argon2id", "bcrypt", "pbkdf2_sha256", "scrypt"]
BCRYPT_MAX_BYTES = 72
SHAPES = {"argon2id": "circle", "bcrypt": "square", "pbkdf2_sha256": "triangle-up", "scrypt": "diamond"}
RUNS = {
    "macos-m4pro-final-2026-10-28": "Mac M4 Pro (main)",
    "windows-ryzen-final-2026-10-28": "Windows Ryzen (replication)",
}
PAGES = [
    "Overview",
    "Environment",
    "RQ1 - Baseline",
    "RQ2 - Parameter sweep",
    "RQ3 - Concurrent login",
    "Statistical analysis",
    "Supplementary (S1-S7)",
    "Mac vs Windows",
    "Conclusion",
    "Live demonstration",
]

CFG = load_config()
SUPP = load_supplementary(CFG)


# ---------------------------------------------------------------- data access


@st.cache_data
def read_csv(path: str) -> pd.DataFrame:
    file = Path(path)
    return pd.read_csv(file) if file.is_file() else pd.DataFrame()


def table(run: str, name: str) -> pd.DataFrame:
    return read_csv(str(ROOT / "runs" / run / "results" / name))


@st.cache_data
def environment(run: str) -> dict:
    return json.loads((ROOT / "runs" / run / "results" / "environment.json").read_text(encoding="utf-8"))


@st.cache_data
def baseline_walls(run: str) -> dict[str, list[float]]:
    """Every measured baseline verification time (ms) from the run's raw data."""
    rows = _latency_table(read_jsonl(ROOT / "runs" / run / "data" / "raw" / "latency.jsonl"))
    return {row["algorithm"]: row["_walls"] for row in rows if "baseline" in row["roles"]}


def web_login(run: str) -> pd.DataFrame:
    """The optional web test, if it was run on the same machine as this run."""
    saved = table(run, "supplementary/web_login.csv")
    if not saved.empty:
        return saved
    root_env = ROOT / "results" / "environment.json"
    if root_env.is_file() and json.loads(root_env.read_text(encoding="utf-8")) == environment(run):
        return read_csv(str(ROOT / "results" / "supplementary" / "web_login.csv"))
    return pd.DataFrame()


def name(algorithm: str) -> str:
    return display_name(algorithm)


def with_names(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["Algorithm"] = frame["algorithm"].map(name)
    if "parameter_name" in frame:
        frame["Parameter"] = [_param_text(n, v) for n, v in zip(frame["parameter_name"], frame["parameter_value"])]
    return frame


def color(present: list[str]) -> alt.Color:
    order = [name(a) for a in ALGORITHMS if a in present]
    return alt.Color(
        "Algorithm:N",
        scale=alt.Scale(domain=order, range=[COLORS[a] for a in ALGORITHMS if a in present]),
        legend=alt.Legend(orient="top", title=None),
    )


def shape(present: list[str]) -> alt.Shape:
    order = [name(a) for a in ALGORITHMS if a in present]
    return alt.Shape(
        "Algorithm:N",
        scale=alt.Scale(domain=order, range=[SHAPES[a] for a in ALGORITHMS if a in present]),
        legend=None,
    )


def chart(spec: alt.Chart) -> None:
    st.altair_chart(spec.properties(height=340), width="stretch")


def meets(p95: float, throughput: float, limit_ms: float) -> bool:
    return p95 <= limit_ms and throughput >= CFG.throughput_min


def reference_rows(concurrency: pd.DataFrame) -> pd.DataFrame:
    rows = concurrency[(concurrency["pool"] == "thread") & (concurrency["workers"] == CFG.reference_workers)].copy()
    return rows[~rows["skipped"].astype(bool)]


def mark(passed: bool) -> str:
    return "pass" if passed else "fail"


# ---------------------------------------------------------------- pages


def page_overview(run: str) -> None:
    st.title("Password Hashing Benchmark")
    st.caption(
        "Experimental comparison of Argon2id, bcrypt, and PBKDF2-HMAC-SHA256 for server-side password verification. "
        "scrypt was added as a supplementary fourth algorithm."
    )
    baseline = table(run, "rq1_baseline.csv")
    columns = st.columns(len(baseline))
    for column, (_, row) in zip(columns, baseline.iterrows()):
        with column:
            st.markdown(f"**{name(row['algorithm'])}**")
            st.caption(_param_text(row["parameter_name"], row["parameter_value"]) + " (OWASP minimum)")
            st.metric("Median verification", f"{row['median_ms']:.2f} ms")
            st.metric("p95", f"{row['p95_ms']:.2f} ms")
    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Research questions")
        st.markdown(
            "1. **RQ1** - How do the algorithms compare in verification latency, CPU time, and memory at the baselines?\n"
            "2. **RQ2** - How does raising each algorithm's main cost parameter change performance and resource use?\n"
            "3. **RQ3** - Which configurations stay inside the registered latency budgets under concurrent verification?"
        )
    with right:
        st.subheader("Design")
        st.markdown(
            f"- {CFG.password_count} synthetic passwords (seed {CFG.seed}), lengths {', '.join(map(str, CFG.password_lengths))}\n"
            "- 10 warmup and 5 pilot verifications discarded, then 25 repeats per password (1000 verifications)\n"
            f"- Budget A: p95 at most {CFG.budget_a_ms:g} ms and at least {CFG.throughput_min:g} verifications/s "
            f"at {CFG.reference_workers} workers; budget B: {CFG.budget_b_ms:g} ms\n"
            f"- Registered design `config/experiment.yaml`, SHA-256 `{CFG.config_sha256[:12]}...`, not changed after results"
        )
    st.info("Synthetic passwords only. The benchmark measures the defender's verification cost and does no password cracking.")


def page_environment(run: str) -> None:
    st.header("Environment")
    env = environment(run)
    facts = {
        "Processor": env.get("cpu_name"),
        "Cores": f"{env.get('cpu_count_physical')} physical, {env.get('cpu_count_logical')} logical",
        "Memory": f"{env.get('ram_bytes', 0) / 1024**3:.1f} GiB",
        "Platform": env.get("platform"),
        "Python": str(env.get("python", "")).split()[0],
        "OpenSSL": env.get("openssl"),
        "Measured at (UTC)": env.get("computer_time_utc"),
        "Registered config SHA-256": env.get("config_sha256"),
    }
    st.table(pd.DataFrame({"Item": list(facts), "Value": [str(value) for value in facts.values()]}).set_index("Item"))
    st.subheader("Library versions")
    st.table(pd.DataFrame({"Library": list(env["libraries"]), "Version": list(env["libraries"].values())}).set_index("Library"))
    with st.expander("Power settings as recorded"):
        st.code(env.get("power_scheme", ""), language=None)


def page_rq1(run: str) -> None:
    st.header("RQ1 - Baseline comparison")
    baseline = with_names(table(run, "rq1_baseline.csv"))
    present = list(baseline["algorithm"])
    bars = alt.Chart(baseline).mark_bar(cornerRadiusEnd=4, size=36).encode(
        y=alt.Y("Algorithm:N", sort=[name(a) for a in present], title=None),
        x=alt.X("median_ms:Q", title="Median verification time (ms)"),
        color=color(present),
        tooltip=["Algorithm", alt.Tooltip("median_ms:Q", format=".2f", title="Median ms"),
                 alt.Tooltip("median_ci_low:Q", format=".2f", title="95% CI low"),
                 alt.Tooltip("median_ci_high:Q", format=".2f", title="95% CI high"),
                 alt.Tooltip("p95_ms:Q", format=".2f", title="p95 ms")],
    )
    errors = alt.Chart(baseline).mark_errorbar(color="#333333").encode(
        y=alt.Y("Algorithm:N", sort=[name(a) for a in present]), x="median_ci_low:Q", x2="median_ci_high:Q"
    )
    chart(bars + errors)
    shown = baseline.assign(
        **{
            "Median ms": baseline["median_ms"].round(2),
            "95% CI": [f"{low:.2f} to {high:.2f}" for low, high in zip(baseline["median_ci_low"], baseline["median_ci_high"])],
            "p95 ms": baseline["p95_ms"].round(2),
            "CPU ms": baseline["median_cpu_ms"].round(2),
            "Memory MiB (measured)": baseline["median_rss_delta_mib"].round(1),
            "Memory MiB (configured)": baseline["configured_memory_mib"],
            "n": baseline["n"],
        }
    )
    st.dataframe(shown[["Algorithm", "Parameter", "Median ms", "95% CI", "p95 ms", "CPU ms", "Memory MiB (measured)", "Memory MiB (configured)", "n"]], hide_index=True)
    order = baseline.sort_values("median_ms")["Algorithm"].tolist()
    st.markdown("**Ranking by median verification time:** " + " < ".join(order))
    st.caption(
        "A shorter verification time is not a security ranking. Each baseline is a different cost setting; "
        "only Argon2id spends memory, which raises the cost of parallel guessing."
    )
    walls = baseline_walls(run)
    if walls:
        st.subheader("Distribution of all 1000 verifications per algorithm")
        frame = pd.DataFrame([(name(a), value) for a, values in walls.items() for value in values], columns=["Algorithm", "ms"])
        box = alt.Chart(frame).mark_boxplot(extent=1.5, size=30).encode(
            y=alt.Y("Algorithm:N", sort=[name(a) for a in present], title=None),
            x=alt.X("ms:Q", title="Verification time (ms)"),
            color=color(present),
        )
        chart(box)


def page_rq2(run: str) -> None:
    st.header("RQ2 - Parameter sweep")
    sweep = with_names(table(run, "rq2_parameter_sweep.csv"))
    algorithm = st.selectbox("Algorithm", [a for a in ALGORITHMS if a in set(sweep["algorithm"])], format_func=name)
    metric = st.radio("Metric", ["Median latency", "p95 latency", "Measured memory"], horizontal=True)
    rows = sweep[sweep["algorithm"] == algorithm].sort_values("parameter_value").copy()
    rows["x"] = [_param_text(n, v) for n, v in zip(rows["parameter_name"], rows["parameter_value"])]
    field, title = {
        "Median latency": ("median_ms", "Median verification time (ms)"),
        "p95 latency": ("p95_ms", "p95 verification time (ms)"),
        "Measured memory": ("median_rss_delta_mib", "Peak memory growth (MiB)"),
    }[metric]
    if metric == "Measured memory" and algorithm != "argon2id":
        st.info(f"{name(algorithm)} has no memory-cost parameter; its measured growth stays near zero.")
    base = alt.Chart(rows).encode(
        x=alt.X("x:N", sort=list(rows["x"]), title=_axis(rows.iloc[0]["parameter_name"])),
        y=alt.Y(f"{field}:Q", title=title),
        tooltip=["x", alt.Tooltip(f"{field}:Q", format=".2f")],
    )
    layers = base.mark_line(color=COLORS[algorithm], strokeWidth=2) + base.mark_point(
        color=COLORS[algorithm], filled=True, size=80, shape=SHAPES[algorithm]
    )
    if field == "median_ms":
        layers += alt.Chart(rows).mark_errorbar(color=COLORS[algorithm]).encode(
            x=alt.X("x:N", sort=list(rows["x"])), y="median_ci_low:Q", y2="median_ci_high:Q"
        )
    chart(layers)
    first, last = rows.iloc[0], rows.iloc[-1]
    st.markdown(
        f"From **{_param_text(first['parameter_name'], first['parameter_value'])}** to "
        f"**{_param_text(last['parameter_name'], last['parameter_value'])}**, the median rose from "
        f"**{first['median_ms']:.2f} ms** to **{last['median_ms']:.2f} ms** ({last['median_ms'] / first['median_ms']:.2f}x)."
    )
    st.dataframe(
        rows.assign(**{"Median ms": rows["median_ms"].round(2), "p95 ms": rows["p95_ms"].round(2),
                       "Memory MiB": rows["median_rss_delta_mib"].round(1), "n": rows["n"]})[
            ["Parameter", "Median ms", "p95 ms", "Memory MiB", "n"]
        ],
        hide_index=True,
    )


def _axis(parameter: str) -> str:
    return {"memory_kib": "Memory", "cost": "bcrypt cost", "iterations": "PBKDF2 iterations", "n": "scrypt N", "time_cost": "Time cost t"}[parameter]


def page_rq3(run: str) -> None:
    st.header("RQ3 - Concurrent login")
    concurrency = with_names(table(run, "rq3_concurrency.csv"))
    threads = concurrency[(concurrency["pool"] == "thread") & ~concurrency["skipped"].astype(bool)]
    configs = list(dict.fromkeys(threads["config_id"]))
    labels = {row["config_id"]: f"{row['Algorithm']} - {row['Parameter']}" for _, row in threads.iterrows()}
    config_id = st.selectbox("Configuration", configs, format_func=labels.get)
    rows = threads[threads["config_id"] == config_id].sort_values("workers")
    algorithm = rows.iloc[0]["algorithm"]
    left, right = st.columns(2)
    with left:
        base = alt.Chart(rows).encode(x=alt.X("workers:O", title="Concurrent workers"),
                                      y=alt.Y("throughput_per_second:Q", title="Verifications per second"),
                                      tooltip=["workers", alt.Tooltip("throughput_per_second:Q", format=".1f")])
        chart(base.mark_bar(color=COLORS[algorithm], cornerRadiusEnd=4, size=40))
    with right:
        base = alt.Chart(rows).encode(x=alt.X("workers:O", title="Concurrent workers"),
                                      y=alt.Y("p95_ms:Q", title="p95 verification time (ms)"),
                                      tooltip=["workers", alt.Tooltip("p95_ms:Q", format=".1f")])
        rule = alt.Chart(pd.DataFrame({"y": [CFG.budget_a_ms]})).mark_rule(strokeDash=[6, 4], color="#555555").encode(y="y:Q")
        chart(base.mark_line(color=COLORS[algorithm]) + base.mark_point(color=COLORS[algorithm], filled=True, size=80) + rule)
        st.caption(f"Dashed line: budget A p95 limit ({CFG.budget_a_ms:g} ms).")
    reference = rows[rows["workers"] == CFG.reference_workers]
    if not reference.empty:
        row = reference.iloc[0]
        a = meets(row["p95_ms"], row["throughput_per_second"], CFG.budget_a_ms)
        b = meets(row["p95_ms"], row["throughput_per_second"], CFG.budget_b_ms)
        st.subheader(f"Budget check at {CFG.reference_workers} workers")
        cols = st.columns(4)
        cols[0].metric("p95", f"{row['p95_ms']:.1f} ms")
        cols[1].metric("Throughput", f"{row['throughput_per_second']:.1f} /s")
        cols[2].metric(f"Budget A ({CFG.budget_a_ms:g} ms)", mark(a).upper())
        cols[3].metric(f"Budget B ({CFG.budget_b_ms:g} ms)", mark(b).upper())

    st.subheader("All registered configurations")
    ref = reference_rows(concurrency)
    memory = table(run, "rq3_concurrent_memory.csv").set_index("config_id") if not table(run, "rq3_concurrent_memory.csv").empty else None
    summary = ref.assign(
        **{
            "p95 ms": ref["p95_ms"].round(1),
            "Per second": ref["throughput_per_second"].round(1),
            "Budget A": [mark(meets(p, t, CFG.budget_a_ms)) for p, t in zip(ref["p95_ms"], ref["throughput_per_second"])],
            "Budget B": [mark(meets(p, t, CFG.budget_b_ms)) for p, t in zip(ref["p95_ms"], ref["throughput_per_second"])],
            "Memory MiB, 4 at once": [round(memory.loc[c, "fresh_peak_delta_mib"], 1) if memory is not None and c in memory.index else None for c in ref["config_id"]],
        }
    )
    st.dataframe(summary[["Algorithm", "Parameter", "p95 ms", "Per second", "Memory MiB, 4 at once", "Budget A", "Budget B"]], hide_index=True)
    passed = sum(value == "pass" for value in summary["Budget A"])
    st.markdown(f"**{passed} of {len(summary)}** configurations meet budget A on this machine.")

    st.subheader("Process-pool check")
    process = concurrency[(concurrency["pool"] == "process")]
    checks = []
    for _, row in process.iterrows():
        thread = threads[(threads["config_id"] == row["config_id"]) & (threads["workers"] == row["workers"])]
        if thread.empty:
            continue
        t, p = thread.iloc[0]["throughput_per_second"], row["throughput_per_second"]
        difference = abs(p - t) / t
        checks.append({"Algorithm": row["Algorithm"], "Thread pool /s": round(t, 1), "Process pool /s": round(p, 1),
                       "Difference": f"{difference:.1%}", "Within 15%": "yes" if difference <= 0.15 else "no - reported as a finding"})
    st.dataframe(pd.DataFrame(checks), hide_index=True)


def page_statistics(run: str) -> None:
    st.header("Statistical analysis")
    walls = baseline_walls(run)
    if len(walls) > 2:
        omnibus = kruskal_wallis(list(walls.values()))
        cols = st.columns(3)
        cols[0].metric("Kruskal-Wallis H", f"{omnibus['h']:.1f}")
        cols[1].metric("p-value", "< 0.0001" if omnibus["p_value"] < 0.0001 else f"{omnibus['p_value']:.4f}")
        cols[2].metric("Effect size epsilon-squared", f"{omnibus['epsilon_squared']:.3f}")
    pairs = table(run, "rq1_statistics.csv")
    algorithms = {row["config_id"]: row["algorithm"] for _, row in table(run, "rq1_baseline.csv").iterrows()}
    shown = pd.DataFrame(
        {
            "Comparison": [f"{name(algorithms[a])} / {name(algorithms[b])}" for a, b in zip(pairs["first"], pairs["second"])],
            "Median ratio": pairs["median_ratio"].round(3),
            "95% CI": [f"{low:.3f} to {high:.3f}" for low, high in zip(pairs["median_ratio_ci_low"], pairs["median_ratio_ci_high"])],
            "Mann-Whitney p (Holm)": ["< 0.0001" if p < 0.0001 else f"{p:.4f}" for p in pairs["p_holm"]],
            "Cliff's delta": pairs["cliffs_delta"].round(3),
            "Magnitude": pairs["cliffs_magnitude"],
        }
    )
    st.dataframe(shown, hide_index=True)
    st.markdown(
        "- **Bootstrap 95% intervals** (10000 resamples) for every median and p95.\n"
        "- **Kruskal-Wallis** tests whether the baselines differ at all; **Mann-Whitney U** compares each pair, "
        "with **Holm** adjustment for three comparisons.\n"
        "- **Cliff's delta** is the size of the difference: -1 means every verification of the first algorithm "
        "was faster than every verification of the second.\n"
        "- With 1000 verifications per algorithm a p-value detects even tiny differences, so the median ratio and "
        "Cliff's delta are what describe the size."
    )


def page_supplementary(run: str) -> None:
    st.header("Supplementary experiments")
    st.caption("Declared in config/supplementary.yaml after the proposal. They extend the registered experiment and do not change its answers.")
    tabs = st.tabs(["S1 scrypt", "S2 Argon2id t", "S3 tight budgets", "S4 saturation", "S5 equal time", "S6 wrong password", "S7 input pitfalls", "Web login (optional)"])
    with tabs[0]:
        four = pd.concat([table(run, "rq1_baseline.csv"), table(run, "supplementary/s1_scrypt.csv").query("parameter_value == @SUPP.baselines()['scrypt']['n']")])
        four = with_names(four)
        present = list(four["algorithm"])
        chart(alt.Chart(four).mark_bar(cornerRadiusEnd=4, size=30).encode(
            y=alt.Y("Algorithm:N", sort=[name(a) for a in present], title=None),
            x=alt.X("median_ms:Q", title="Median verification time (ms)"), color=color(present),
            tooltip=["Algorithm", "Parameter", alt.Tooltip("median_ms:Q", format=".2f"), alt.Tooltip("median_rss_delta_mib:Q", format=".1f", title="Memory MiB")]))
        sweep = with_names(table(run, "supplementary/s1_scrypt.csv"))
        st.dataframe(sweep.assign(**{"Median ms": sweep["median_ms"].round(2), "p95 ms": sweep["p95_ms"].round(2), "Memory MiB": sweep["median_rss_delta_mib"].round(1)})[["Parameter", "Median ms", "p95 ms", "Memory MiB"]], hide_index=True)
        st.caption("scrypt baseline is the OWASP minimum N=2^17, r=8, p=1 (128 MiB).")
    with tabs[1]:
        t_sweep = table(run, "supplementary/s2_argon2id_time_cost.csv")
        base = alt.Chart(t_sweep).encode(x=alt.X("parameter_value:O", title="Time cost t (memory fixed at 19 MiB)"), y=alt.Y("median_ms:Q", title="Median verification time (ms)"))
        chart(base.mark_line(color=COLORS["argon2id"]) + base.mark_point(color=COLORS["argon2id"], filled=True, size=80))
        st.caption("Time grows linearly with t while memory stays at 19 MiB.")
    with tabs[2]:
        workers = table(run, "supplementary/s4_concurrency_all_workers.csv")
        ref = with_names(reference_rows(workers))
        budgets = SUPP.tight_budgets_ms
        ref = ref.assign(**{f"{limit:g} ms": [mark(meets(p, t, limit)) for p, t in zip(ref["p95_ms"], ref["throughput_per_second"])] for limit in budgets})
        ref["config"] = ref["config_id"]
        st.dataframe(ref.assign(**{"p95 ms": ref["p95_ms"].round(1), "Per second": ref["throughput_per_second"].round(1)})[["Algorithm", "config", "p95 ms", "Per second"] + [f"{limit:g} ms" for limit in budgets]], hide_index=True)
        for limit in budgets:
            st.markdown(f"Inside **{limit:g} ms**: {sum(ref[f'{limit:g} ms'] == 'pass')} of {len(ref)} configurations.")
    with tabs[3]:
        workers = with_names(table(run, "supplementary/s4_concurrency_all_workers.csv"))
        workers = workers[(workers["pool"] == "thread") & ~workers["skipped"].astype(bool)]
        baseline_ids = list(table(run, "rq1_baseline.csv")["config_id"]) + [c for c in workers["config_id"].unique() if c.startswith("scrypt-n131072")]
        chosen = st.multiselect("Configurations", sorted(workers["config_id"].unique()), default=baseline_ids)
        rows = workers[workers["config_id"].isin(chosen)]
        present = list(dict.fromkeys(rows["algorithm"]))
        base = alt.Chart(rows).encode(
            x=alt.X("workers:Q", scale=alt.Scale(type="log", base=2), axis=alt.Axis(values=sorted(rows["workers"].unique())), title="Concurrent workers (log scale)"),
            y=alt.Y("throughput_per_second:Q", title="Verifications per second"),
            detail="config_id:N", color=color(present),
            tooltip=["config_id", "workers", alt.Tooltip("throughput_per_second:Q", format=".1f"), alt.Tooltip("p95_ms:Q", format=".1f")])
        logical = environment(run).get("cpu_count_logical")
        rule = alt.Chart(pd.DataFrame({"x": [logical]})).mark_rule(strokeDash=[6, 4], color="#555555").encode(x="x:Q")
        chart(base.mark_line() + base.mark_point(filled=True, size=60).encode(shape=shape(present)) + rule)
        st.caption(f"Dashed line: this machine's {logical} logical CPUs. Throughput stops rising near the core count.")
    with tabs[4]:
        equal = with_names(table(run, "supplementary/s5_equal_latency.csv"))
        target = st.radio("Target median", sorted(equal["target_ms"].unique()), format_func=lambda v: f"{v:g} ms", horizontal=True)
        rows = equal[equal["target_ms"] == target]
        present = list(rows["algorithm"])
        chart(alt.Chart(rows).mark_bar(cornerRadiusEnd=4, size=30).encode(
            y=alt.Y("Algorithm:N", sort=[name(a) for a in present], title=None),
            x=alt.X("median_rss_delta_mib:Q", title="Memory per verification at the same time (MiB)"), color=color(present),
            tooltip=["Algorithm", "Parameter", alt.Tooltip("median_ms:Q", format=".1f")]))
        st.dataframe(rows.assign(**{"Median ms": rows["median_ms"].round(1), "Deviation": [f"{d:+.1%}" for d in rows["deviation"]], "Memory MiB": rows["median_rss_delta_mib"].round(1)})[["Algorithm", "Parameter", "Median ms", "Deviation", "Memory MiB"]], hide_index=True)
        st.caption("At the same verification time, the memory-hard algorithms make every guess also hold memory. bcrypt cost and scrypt N double per step, so they can miss the target.")
    with tabs[5]:
        wrong = with_names(table(run, "supplementary/s6_wrong_password.csv"))
        st.dataframe(wrong.assign(**{"Correct ms": wrong["correct_median_ms"].round(3), "Wrong ms": wrong["wrong_median_ms"].round(3), "Difference ms": wrong["difference_ms"].round(3),
                                     "95% CI": [f"{l:+.3f} to {h:+.3f}" for l, h in zip(wrong["difference_ci_low"], wrong["difference_ci_high"])],
                                     "Equivalent (within 2%)": ["yes" if e else "no" for e in wrong["equivalent"]]})[["Algorithm", "Correct ms", "Wrong ms", "Difference ms", "95% CI", "Equivalent (within 2%)"]], hide_index=True)
        st.caption("A wrong password costs the same full derivation as a correct one. Millisecond timing cannot resolve the final comparison step.")
    with tabs[6]:
        inputs = table(run, "supplementary/s7_input_handling.csv")
        inputs["Result"] = ["rejected" if isinstance(e, str) and e else ("same key" if s else "different") for s, e in zip(inputs["same_result"], inputs["error"])]
        pivot = inputs.pivot(index="algorithm", columns="name", values="Result").reindex([a for a in ALGORITHMS if a in set(inputs["algorithm"])])
        pivot.index = [name(a) for a in pivot.index]
        st.dataframe(pivot)
        st.caption("HMAC hashes keys longer than 64 bytes and zero-pads shorter ones, so PBKDF2 and scrypt accept P and SHA256(P), and P with a trailing NUL, as the same password.")
    with tabs[7]:
        web = web_login(run)
        if web.empty:
            st.info("The optional web login test was not run on this machine.")
        else:
            web = with_names(web)
            st.dataframe(web.assign(**{"Requests/s": web["requests_per_second"].round(1), "Correct median ms": web["correct_median_ms"], "Correct p95 ms": web["correct_p95_ms"], "Failures": web["failures"]})[["Algorithm", "clients", "Requests/s", "Correct median ms", "Correct p95 ms", "Failures"]], hide_index=True)
            st.caption("FastAPI POST /login under locust clients on the same machine. Declared after the final runs; orientation only.")


def page_compare() -> None:
    st.header("Mac vs Windows - independent replication")
    mac, win = list(RUNS)
    frames = {run: table(run, "rq1_baseline.csv").set_index("algorithm") for run in RUNS}
    rows = []
    for algorithm in frames[mac].index:
        m, w = frames[mac].loc[algorithm, "median_ms"], frames[win].loc[algorithm, "median_ms"]
        rows.append({"Algorithm": name(algorithm), "Mac M4 Pro ms": round(m, 2), "Windows Ryzen ms": round(w, 2), "Windows / Mac": f"{w / m:.2f}x"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    long = pd.DataFrame([{"Algorithm": name(a), "Machine": RUNS[run].split(" (")[0], "Median ms": frames[run].loc[a, "median_ms"]} for run in RUNS for a in frames[run].index])
    chart(alt.Chart(long).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("Machine:N", title=None), x=alt.X("Median ms:Q", title="Median verification time (ms)"),
        color=color(list(frames[mac].index)), row=alt.Row("Algorithm:N", title=None, sort=[name(a) for a in frames[mac].index]),
        tooltip=["Algorithm", "Machine", alt.Tooltip("Median ms:Q", format=".2f")]).properties(height=60))
    for run in RUNS:
        order = frames[run].sort_values("median_ms").index
        st.markdown(f"**{RUNS[run].split(' (')[0]}:** " + " < ".join(name(a) for a in order))
    same = list(frames[mac].sort_values("median_ms").index) == list(frames[win].sort_values("median_ms").index)
    (st.success if same else st.warning)("Ranking replicated on both machines." if same else "Ranking differs between machines.")
    verdicts = {}
    for run in RUNS:
        ref = reference_rows(table(run, "rq3_concurrency.csv"))
        verdicts[run] = {c: meets(p, t, CFG.budget_a_ms) for c, p, t in zip(ref["config_id"], ref["p95_ms"], ref["throughput_per_second"])}
    shared = [c for c in verdicts[mac] if c in verdicts[win]]
    cols = st.columns(3)
    cols[0].metric("Budget A on Mac", f"{sum(verdicts[mac][c] for c in shared)} of {len(shared)}")
    cols[1].metric("Budget A on Windows", f"{sum(verdicts[win][c] for c in shared)} of {len(shared)}")
    cols[2].metric("Same verdict", f"{sum(verdicts[mac][c] == verdicts[win][c] for c in shared)} of {len(shared)}")
    st.caption(
        "Same source and configuration on both machines, each run independently. The machines differ in processor, "
        "operating system, and Python build, so the differences are not attributed to the operating system alone. "
        "Full table: comparisons/macos-m4pro-final-2026-10-28__windows-ryzen-final-2026-10-28/comparison.md."
    )


def page_conclusion() -> None:
    st.header("Conclusion")
    mac, win = list(RUNS)
    lines = []
    for run in RUNS:
        baseline = table(run, "rq1_baseline.csv").sort_values("median_ms")
        ref = reference_rows(table(run, "rq3_concurrency.csv"))
        passed = sum(meets(p, t, CFG.budget_a_ms) for p, t in zip(ref["p95_ms"], ref["throughput_per_second"]))
        lines.append(f"- **{RUNS[run].split(' (')[0]}:** " + " < ".join(f"{name(r.algorithm)} {r.median_ms:.1f} ms" for r in baseline.itertuples())
                     + f"; {passed} of {len(ref)} configurations meet budget A.")
    st.markdown(
        "**RQ1.** At the OWASP baselines the ranking by verification time was the same on both machines:\n" + "\n".join(lines)
        + "\n\n**RQ2.** Cost grows as configured: bcrypt doubles per cost step, PBKDF2 grows linearly with iterations, "
        "and Argon2id grows with memory, which it also measurably uses.\n\n"
        "**RQ3.** Most configurations fit the registered budgets at 4 workers; the tighter supplementary budgets "
        "(100 and 250 ms) separate them clearly.\n\n"
        "**Limits.** Results are specific to these machines, library versions, and configurations. A faster "
        "verification is not a stronger hash: the baselines are different cost settings, and attacker hardware "
        "was not measured."
    )


def page_demo() -> None:
    st.header("Live demonstration")
    st.warning("Demonstration only. These timings come from the presenting machine, which is not idle; the results in the other pages come from the saved runs.")
    algorithm = st.selectbox("Algorithm (baseline parameters)", ALGORITHMS, format_func=name)
    password = st.text_input("Password to store (use a made-up one)", "synthetic-demo-password")
    count = st.slider("Verifications", 3, 20, 5)
    too_long = algorithm == "bcrypt" and len(password.encode("utf-8")) > BCRYPT_MAX_BYTES
    if too_long:
        st.error(f"bcrypt accepts at most {BCRYPT_MAX_BYTES} bytes. Use a shorter password.")
    if st.button("Run demonstration", disabled=not password or too_long):
        params = SUPP.baselines()[algorithm]
        hasher = make_hasher(algorithm, params)
        encoded = hasher.hash_password(password)
        times = []
        progress = st.progress(0.0)
        for index in range(count):
            start = time.perf_counter()
            hasher.verify(password, encoded)
            times.append((time.perf_counter() - start) * 1000)
            progress.progress((index + 1) / count)
        st.session_state["demo"] = {"algorithm": algorithm, "params": params, "encoded": encoded, "times": times}
    demo = st.session_state.get("demo")
    if not demo or demo["algorithm"] != algorithm:
        return
    cols = st.columns(2)
    cols[0].metric("Median", f"{statistics.median(demo['times']):.1f} ms")
    cols[1].metric("Fastest", f"{min(demo['times']):.1f} ms")
    st.markdown("**Stored hash** - the server keeps only this, never the password:")
    st.code(demo["encoded"], language=None)

    st.subheader("Try a password against the stored hash")
    candidate = st.text_input("Password to check", key="candidate")
    if candidate:
        size = len(candidate.encode("utf-8"))
        if demo["algorithm"] == "bcrypt" and size > BCRYPT_MAX_BYTES:
            st.error(f"Rejected before hashing: bcrypt accepts at most {BCRYPT_MAX_BYTES} bytes and this password has {size}.")
            return
        hasher = make_hasher(demo["algorithm"], demo["params"])
        start = time.perf_counter()
        matched = hasher.verify(candidate, demo["encoded"])
        elapsed = (time.perf_counter() - start) * 1000
        if matched:
            st.success(f"Accepted - correct password ({elapsed:.1f} ms)")
        else:
            st.error(f"Rejected - wrong password ({elapsed:.1f} ms)")


# ---------------------------------------------------------------- layout

st.set_page_config(page_title="Password Hashing Benchmark", layout="wide")
with st.sidebar:
    st.markdown("### Password Hashing Benchmark")
    page = st.radio("Section", PAGES, label_visibility="collapsed")
    run = st.selectbox("Saved run", list(RUNS), format_func=RUNS.get, disabled=page in {"Mac vs Windows", "Conclusion", "Live demonstration"})
    st.caption("Reads runs/ only. Synthetic passwords; no cracking.")

{
    "Overview": lambda: page_overview(run),
    "Environment": lambda: page_environment(run),
    "RQ1 - Baseline": lambda: page_rq1(run),
    "RQ2 - Parameter sweep": lambda: page_rq2(run),
    "RQ3 - Concurrent login": lambda: page_rq3(run),
    "Statistical analysis": lambda: page_statistics(run),
    "Supplementary (S1-S7)": lambda: page_supplementary(run),
    "Mac vs Windows": page_compare,
    "Conclusion": page_conclusion,
    "Live demonstration": page_demo,
}[page]()
