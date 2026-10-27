"""Record the machine and library versions that the results belong to."""

import importlib.metadata
import json
import platform
import ssl
import subprocess
import sys
from datetime import datetime, timezone

import psutil

from password_benchmark import __version__


PACKAGES = ("argon2-cffi", "bcrypt", "psutil", "pandas", "matplotlib", "PyYAML")


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _cpu_name() -> str:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return platform.processor() or platform.machine()
    command = (
        ["sysctl", "-n", "machdep.cpu.brand_string"]
        if system == "Darwin"
        else ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        output = subprocess.check_output(
            command,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
        name = " ".join(output.split())
        if name:
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or platform.machine()


def _power_scheme() -> str:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return "not collected on this platform"
    command = ["pmset", "-g", "custom"] if system == "Darwin" else ["powercfg", "/getactivescheme"]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        output = subprocess.check_output(
            command,
            text=True,
            timeout=20,
            creationflags=creationflags,
        )
        return " ".join(output.split())
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {exc}"


def _pip_freeze() -> list[str]:
    try:
        output = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in output.splitlines() if line.strip()]


def _cpu_frequency() -> dict | None:
    # Apple Silicon frequency readings from psutil are not reliable MHz.
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return None
    try:
        freq = psutil.cpu_freq()
    except Exception:
        return None
    if freq is None:
        return None
    return {"current_mhz": freq.current, "min_mhz": freq.min, "max_mhz": freq.max}


def collect_environment(cfg, design: str) -> dict:
    return {
        "computer_time_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": cfg.config_sha256,
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_frequency_mhz": _cpu_frequency(),
        "cpu_name": _cpu_name(),
        "design": design,
        "implementation": platform.python_implementation(),
        "libraries": {name: _package_version(name) for name in PACKAGES},
        "machine": platform.machine(),
        "openssl": ssl.OPENSSL_VERSION,
        "pip_freeze": _pip_freeze(),
        "platform": platform.platform(),
        "power_scheme": _power_scheme(),
        "processor": platform.processor(),
        "python": sys.version,
        "ram_bytes": psutil.virtual_memory().total,
        "schema_version": 1,
        "benchmark_version": __version__,
    }


def run_environment(cfg, results_dir, design: str) -> dict:
    results_dir.mkdir(parents=True, exist_ok=True)
    document = collect_environment(cfg, design)
    (results_dir / "environment.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded environment in {results_dir / 'environment.json'}", flush=True)
    return document
