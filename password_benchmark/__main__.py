"""Command entry points for the registered experiment and the pipeline check."""

import os
import sys
from pathlib import Path

from password_benchmark.config import load_config, smoke_config
from password_benchmark.paths import ROOT, output_dirs, supplementary_dirs

REGISTERED_PHASES = ["environment", "bcrypt-length", "latency", "concurrent", "analyze"]
SUPPLEMENTARY_PHASES = ["supp-latency", "supp-concurrent", "equal-latency", "wrong-password", "input-handling", "analyze"]


class RunLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        if self.path.exists():
            raise SystemExit(
                f"A run appears to be in progress ({self.path}). If no run is active, delete that file and start again."
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("running\n", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.path.unlink(missing_ok=True)
        return False


def _prepare_process() -> None:
    os.chdir(ROOT)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def print_help() -> None:
    print("Usage: python -m password_benchmark <command>")
    print()
    print("  smoke           Check the pipeline. Do not use the output in the report.")
    print("  estimate        Time a few registered hashes and estimate the full run.")
    print("  environment     Record the machine and library versions.")
    print("  bcrypt-length   Run the bcrypt 72-byte input experiment.")
    print("  latency         Run verification latency and memory measurement.")
    print("  concurrent      Run the concurrent throughput experiment.")
    print("  analyze         Build tables, figures, and both summaries from collected data.")
    print("  all             Run the registered experiment, then analyze it.")
    print()
    print("  Supplementary experiments (config/supplementary.yaml, reported separately):")
    print("  supp-latency    scrypt and Argon2id time-cost latency and memory.")
    print("  supp-concurrent 16 and 32 workers for the registered configurations; scrypt concurrency.")
    print("  equal-latency   Calibrate every algorithm to the same verification time and measure it.")
    print("  wrong-password  Correct versus wrong password verification time.")
    print("  input-handling  HMAC pre-hash and trailing NUL input pairs.")
    print("  supplementary   Run every supplementary phase, then analyze.")
    print()
    print("  final           Run 'all' and then 'supplementary' in one unattended run.")
    print("  save-run NAME   Save raw data, results, and source in runs/NAME; refuses overwrite.")
    print("  compare A B ... Place saved runs side by side in comparisons/A__B; measures nothing.")
    print()
    print("  Optional (config/web_login.yaml, needs requirements-web.txt; not part of 'final'):")
    print("  web-load        FastAPI /login under locust clients, then write results/supplementary/web_login.md.")
    print()
    print("Run commands from the project root. Close other applications before 'all'.")


def _execute(cfg, raw_dir: Path, results_dir: Path, design: str, phases: list[str], supp, smoke: bool = False) -> int:
    from password_benchmark.bcrypt_length import run_bcrypt_length
    from password_benchmark.concurrent import run_concurrent
    from password_benchmark.environment import run_environment
    from password_benchmark.latency import run_latency

    status = 0
    if "environment" in phases:
        run_environment(cfg, results_dir, design)
    if "bcrypt-length" in phases:
        status |= run_bcrypt_length(cfg, raw_dir, results_dir, design)
    if "latency" in phases:
        status |= run_latency(cfg, raw_dir, results_dir, design)
    if "concurrent" in phases:
        status |= run_concurrent(cfg, raw_dir, results_dir, design)
    status |= _execute_supplementary(supp, phases, smoke)
    if "analyze" in phases:
        from password_benchmark.analyze import run_analyze

        statistics = {"bootstrap_resamples": supp.bootstrap_resamples, "confidence": supp.confidence, "seed": supp.statistics_seed}
        status |= run_analyze(cfg, raw_dir, results_dir, design, statistics)
        supp_raw, supp_results = supplementary_dirs(smoke)
        if supp_raw.is_dir() and any(supp_raw.glob("*.jsonl")):
            from password_benchmark.analyze_supplementary import run_analyze_supplementary

            status |= run_analyze_supplementary(
                supp, raw_dir, results_dir, supp_raw, supp_results, "smoke" if smoke else "supplementary", design
            )
    return status


def _execute_supplementary(supp, phases: list[str], smoke: bool) -> int:
    from password_benchmark.cases import build_cases
    from password_benchmark.concurrent import run_concurrent
    from password_benchmark.equal_latency import run_equal_latency
    from password_benchmark.input_handling import run_input_handling
    from password_benchmark.latency import run_latency
    from password_benchmark.wrong_password import run_wrong_password

    raw_dir, results_dir = supplementary_dirs(smoke)
    design = "smoke" if smoke else "supplementary"
    status = 0
    if "supp-latency" in phases:
        status |= run_latency(supp.extension, raw_dir, results_dir, design)
    if "supp-concurrent" in phases:
        status |= run_concurrent(
            supp.main,
            raw_dir,
            results_dir,
            design,
            workers=supp.extra_workers,
            process_check=False,
            memory_probe=False,
            filename="concurrent_extra.jsonl",
            experiment="concurrent_extra",
        )
        scrypt_cases = [case for case in build_cases(supp.extension) if case.algorithm == "scrypt"]
        status |= run_concurrent(
            supp.extension,
            raw_dir,
            results_dir,
            design,
            cases=scrypt_cases,
            workers=supp.main.concurrency_workers + supp.extra_workers,
        )
    if "equal-latency" in phases:
        status |= run_equal_latency(supp, raw_dir, results_dir, design)
    if "wrong-password" in phases:
        status |= run_wrong_password(supp, raw_dir, results_dir, design)
    if "input-handling" in phases:
        status |= run_input_handling(supp, raw_dir, results_dir, design)
    return status


def main(argv: list[str] | None = None) -> int:
    _prepare_process()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) == 2 and arguments[0] == "save-run":
        from password_benchmark.archive import save_run

        try:
            destination = save_run(arguments[1])
        except (ValueError, OSError, RuntimeError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Saved run in {destination}", flush=True)
        return 0
    if len(arguments) >= 3 and arguments[0] == "compare":
        from password_benchmark.compare import compare_runs

        try:
            destination = compare_runs(arguments[1:])
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Wrote {destination / 'comparison.md'}", flush=True)
        return 0
    if len(arguments) != 1 or arguments[0] in {"-h", "--help", "help"}:
        print_help()
        return 0 if arguments and arguments[0] in {"-h", "--help", "help"} else 1

    command = arguments[0]
    from password_benchmark.supplementary import load_supplementary, smoke_supplementary

    if command == "smoke":
        cfg = smoke_config(load_config())
        raw_dir, results_dir = output_dirs(True)
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "NOT_FOR_REPORT.txt").write_text(
            "Pipeline check only. Do not use these figures or tables in the report.\n",
            encoding="utf-8",
        )
        print("SMOKE TEST ONLY. Output goes to results/smoke and must not be used in the report.", flush=True)
        supp = smoke_supplementary(load_supplementary())
        with RunLock(results_dir / "RUN_IN_PROGRESS"):
            return _execute(cfg, raw_dir, results_dir, "smoke", REGISTERED_PHASES + SUPPLEMENTARY_PHASES, supp, smoke=True)

    cfg = load_config()
    supp = load_supplementary(cfg)
    raw_dir, results_dir = output_dirs(False)
    if command == "estimate":
        from password_benchmark.estimate import run_estimate

        run_estimate(cfg, results_dir)
        return 0
    if command == "environment":
        return 0 if _execute(cfg, raw_dir, results_dir, "registered", ["environment"], supp) == 0 else 1
    if command == "analyze":
        if (results_dir / "RUN_IN_PROGRESS").exists():
            raise SystemExit("A measurement run is in progress. Wait for it to finish before analyzing.")
        return _execute(cfg, raw_dir, results_dir, "registered", ["analyze"], supp)
    if command == "web-load":
        from importlib.util import find_spec

        missing = [name for name in ("fastapi", "uvicorn", "locust") if find_spec(name) is None]
        if missing:
            raise SystemExit(f"Missing {', '.join(missing)}. Install the optional packages: python -m pip install -r requirements-web.txt")
        from password_benchmark.web_load import analyze_web_load, load_web_settings, run_web_load

        settings = load_web_settings()
        supp_raw, supp_results = supplementary_dirs(False)
        print("Optional web login load test. Leave this machine idle until the process exits.", flush=True)
        with RunLock(results_dir / "RUN_IN_PROGRESS"):
            status = run_web_load(settings, supp, supp_raw, supp_results)
        return status | analyze_web_load(settings, cfg, supp_raw, supp_results)

    phases = {
        "bcrypt-length": ["bcrypt-length"],
        "latency": ["latency"],
        "concurrent": ["concurrent"],
        "all": REGISTERED_PHASES,
        "supp-latency": ["supp-latency"],
        "supp-concurrent": ["supp-concurrent"],
        "equal-latency": ["equal-latency"],
        "wrong-password": ["wrong-password"],
        "input-handling": ["input-handling"],
        "supplementary": SUPPLEMENTARY_PHASES,
        "final": REGISTERED_PHASES[:-1] + SUPPLEMENTARY_PHASES,
    }
    if command not in phases:
        print_help()
        return 1
    if command in {"all", "final"}:
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "run_log.txt").write_text("", encoding="utf-8")
        print("Registered experiment. Leave this machine idle until the process exits.", flush=True)
    if command in {"supplementary", "final"}:
        supp_results = supplementary_dirs(False)[1]
        supp_results.mkdir(parents=True, exist_ok=True)
        (supp_results / "run_log.txt").write_text("", encoding="utf-8")
        print("Supplementary experiments are included. Leave this machine idle until the process exits.", flush=True)
    with RunLock(results_dir / "RUN_IN_PROGRESS"):
        return _execute(cfg, raw_dir, results_dir, "registered", phases[command], supp)


if __name__ == "__main__":
    sys.exit(main())
