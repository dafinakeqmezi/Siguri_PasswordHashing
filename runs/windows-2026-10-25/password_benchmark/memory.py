"""Measure the resident set of one verification from a fresh process."""

import json
import os
import queue
import subprocess
import sys
import threading

from password_benchmark.paths import ROOT


class MemoryProbeError(RuntimeError):
    pass


def _read_json(line_queue: "queue.Queue[str]", timeout: float) -> dict:
    try:
        line = line_queue.get(timeout=timeout)
    except queue.Empty as exc:
        raise MemoryProbeError("Memory worker timed out") from exc
    if not line:
        raise MemoryProbeError("Memory worker closed its output")
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise MemoryProbeError(f"Memory worker returned invalid output: {line!r}") from exc


def probe_verify_rss(algorithm: str, params: dict, password: str, encoded: str, timeout: float = 180) -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "password_benchmark.mem_worker"],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    lines: queue.Queue[str] = queue.Queue()
    errors: list[str] = []

    def read_stdout() -> None:
        for line in process.stdout:
            lines.put(line)

    def read_stderr() -> None:
        errors.append(process.stderr.read())

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        process.stdin.write(json.dumps({"algorithm": algorithm, "params": params, "password": password, "encoded": encoded}) + "\n")
        process.stdin.flush()
        ready = _read_json(lines, timeout)
        if ready.get("event") != "ready":
            raise MemoryProbeError(f"Memory worker was not ready: {ready}")
        process.stdin.write("go\n")
        process.stdin.flush()
        done = _read_json(lines, timeout)
        process.wait(timeout=30)
        if done.get("event") != "done":
            raise MemoryProbeError(f"Memory worker returned an unexpected event: {done}")
        if done.get("error"):
            detail = "".join(errors).strip()
            message = str(done["error"])
            if detail:
                message = f"{message} ({detail})"
            raise MemoryProbeError(message)
        return {
            "baseline_rss": int(done["baseline_rss"]),
            "delta_rss": int(done["delta_rss"]),
            "ok": bool(done.get("ok")),
            "peak_rss": int(done["peak_rss"]),
        }
    except Exception:
        if process.poll() is None:
            process.kill()
        raise
    finally:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        stderr_thread.join(timeout=1)
        stdout_thread.join(timeout=1)


def should_skip_for_memory(needed_bytes: int, available_bytes: int, factor: float = 1.3) -> bool:
    return needed_bytes > 0 and needed_bytes * factor > available_bytes
