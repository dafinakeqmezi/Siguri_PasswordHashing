"""JSONL reading and writing for raw measurements."""

import json
from pathlib import Path


def reset_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path.name} line {line_number}") from exc
    return rows


def drop_experiment(path: Path, experiment: str) -> None:
    kept = [row for row in read_jsonl(path) if row.get("experiment") != experiment]
    reset_file(path)
    for row in kept:
        append_jsonl(path, row)


def log_line(results_dir: Path, message: str) -> None:
    print(message, flush=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / "run_log.txt").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(message + "\n")
