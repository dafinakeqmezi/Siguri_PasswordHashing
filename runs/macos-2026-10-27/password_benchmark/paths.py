"""Project paths. All commands run against these locations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "experiment.yaml"


def output_dirs(smoke: bool) -> tuple[Path, Path]:
    if smoke:
        return ROOT / "data" / "smoke", ROOT / "results" / "smoke"
    return ROOT / "data" / "raw", ROOT / "results"
