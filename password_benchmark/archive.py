"""Save a named copy of the current results without replacing earlier runs."""

import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from password_benchmark.paths import ROOT


def save_run(name: str, root: Path = ROOT) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise ValueError("Run name must contain only letters, digits, hyphens, or underscores (1–80 characters).")
    destination = root / "runs" / name
    if destination.exists():
        raise FileExistsError(f"Saved run already exists: {destination}. Choose another name.")
    if (root / "results" / "RUN_IN_PROGRESS").exists():
        raise RuntimeError("Wait for the measurement run to finish before saving it.")
    for path in (root / "data" / "raw" / "latency.jsonl", root / "results" / "environment.json", root / "results" / "summary.md"):
        if not path.is_file():
            raise FileNotFoundError(f"Missing run output: {path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".saving-", dir=destination.parent) as temporary:
        stage = Path(temporary) / name
        shutil.copytree(root / "data" / "raw", stage / "data" / "raw")
        shutil.copytree(root / "results", stage / "results", ignore=shutil.ignore_patterns("smoke", "runtime_estimate.json", "RUN_IN_PROGRESS"))
        for folder in ("config", "password_benchmark", "tests"):
            shutil.copytree(root / folder, stage / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for filename in ("README.md", "requirements.txt", "requirements-lock.txt"):
            shutil.copy2(root / filename, stage / filename)
        write_manifest(stage, {
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_note": "Source captured when saving. If code changed after measurement, this source may differ from the code used to collect the results.",
        })
        stage.rename(destination)
    return destination


def write_manifest(folder: Path, metadata: dict) -> None:
    metadata = dict(metadata)
    metadata["sha256"] = {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path != folder / "manifest.json"
    }
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
