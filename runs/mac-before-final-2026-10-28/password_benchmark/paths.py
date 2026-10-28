"""Project paths. All commands run against these locations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "experiment.yaml"
SUPPLEMENTARY_PATH = ROOT / "config" / "supplementary.yaml"


def output_dirs(smoke: bool) -> tuple[Path, Path]:
    if smoke:
        return ROOT / "data" / "smoke", ROOT / "results" / "smoke"
    return ROOT / "data" / "raw", ROOT / "results"


def supplementary_dirs(smoke: bool) -> tuple[Path, Path]:
    raw_dir, results_dir = output_dirs(smoke)
    return raw_dir / "supplementary", results_dir / "supplementary"
