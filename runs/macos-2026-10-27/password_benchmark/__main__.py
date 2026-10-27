"""Command entry points for the registered experiment and the pipeline check."""

import os
import sys
from pathlib import Path

from password_benchmark.config import load_config, smoke_config
from password_benchmark.paths import ROOT, output_dirs


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
    print("  analyze         Build tables, figures, and summary.md from collected data.")
    print("  all             Run the registered experiment, then analyze it.")
    print()
    print("Run commands from the project root. Close other applications before 'all'.")


def _execute(cfg, raw_dir: Path, results_dir: Path, design: str, phases: list[str]) -> int:
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
    if "analyze" in phases:
        from password_benchmark.analyze import run_analyze

        status |= run_analyze(cfg, raw_dir, results_dir, design)
    return status


def main(argv: list[str] | None = None) -> int:
    _prepare_process()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or arguments[0] in {"-h", "--help", "help"}:
        print_help()
        return 0 if arguments and arguments[0] in {"-h", "--help", "help"} else 1

    command = arguments[0]
    if command == "smoke":
        cfg = smoke_config(load_config())
        raw_dir, results_dir = output_dirs(True)
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "NOT_FOR_REPORT.txt").write_text(
            "Pipeline check only. Do not use these figures or tables in the report.\n",
            encoding="utf-8",
        )
        print("SMOKE TEST ONLY. Output goes to results/smoke and must not be used in the report.", flush=True)
        with RunLock(results_dir / "RUN_IN_PROGRESS"):
            return _execute(cfg, raw_dir, results_dir, "smoke", ["environment", "bcrypt-length", "latency", "concurrent", "analyze"])

    cfg = load_config()
    raw_dir, results_dir = output_dirs(False)
    if command == "estimate":
        from password_benchmark.estimate import run_estimate

        run_estimate(cfg, results_dir)
        return 0
    if command == "environment":
        return 0 if _execute(cfg, raw_dir, results_dir, "registered", ["environment"]) == 0 else 1
    if command == "analyze":
        if (results_dir / "RUN_IN_PROGRESS").exists():
            raise SystemExit("A measurement run is in progress. Wait for it to finish before analyzing.")
        return _execute(cfg, raw_dir, results_dir, "registered", ["analyze"])

    phases = {
        "bcrypt-length": ["bcrypt-length"],
        "latency": ["latency"],
        "concurrent": ["concurrent"],
        "all": ["environment", "bcrypt-length", "latency", "concurrent", "analyze"],
    }
    if command not in phases:
        print_help()
        return 1
    if command == "all":
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "run_log.txt").write_text("", encoding="utf-8")
        print("Registered experiment. Leave this machine idle until the process exits.", flush=True)
    with RunLock(results_dir / "RUN_IN_PROGRESS"):
        return _execute(cfg, raw_dir, results_dir, "registered", phases[command])


if __name__ == "__main__":
    sys.exit(main())
