"""Optional end-to-end login load test: FastAPI /login under locust.

config/web_login.yaml was declared after the final runs. It does not change the
registered or supplementary designs, and `final` does not run it. Output goes
to data/raw/supplementary/web_login.jsonl and results/supplementary/web_login.*.

Client and server share one machine, so the clients' own CPU use competes with
the hashing. The numbers describe this setup, not a deployed service.
"""

import csv
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

from password_benchmark.analyze import _fmt, _md_table, _write_csv
from password_benchmark.cases import display_name, make_config_id
from password_benchmark.config import file_sha256, yaml
from password_benchmark.hashers import make_hasher
from password_benchmark.io_utils import append_jsonl, drop_experiment, log_line, read_jsonl, reset_file
from password_benchmark.passwords import generate_passwords
from password_benchmark.paths import ROOT
from password_benchmark.wrong_password import wrong_variant

WEB_LOGIN_PATH = ROOT / "config" / "web_login.yaml"
LOCUSTFILE = Path(__file__).with_name("web_locustfile.py")
STAT_NAMES = {"/login": "correct", "/login wrong": "wrong", "Aggregated": "all"}


def load_web_settings(path: Path = WEB_LOGIN_PATH) -> dict:
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings["sha256"] = file_sha256(path)
    return settings


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _post_login(url: str, username: str, password: str) -> int:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    request = urllib.request.Request(f"{url}/login", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _wait_until_ready(url: str, server: subprocess.Popen, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"Server exited with code {server.returncode} before it was ready")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("Server did not become ready")


def parse_locust_stats(path: Path) -> dict[str, dict]:
    """Rows of a locust *_stats.csv, keyed by correct / wrong / all. Times are in ms."""
    found = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            kind = STAT_NAMES.get(row["Name"])
            if kind is None:
                continue
            found[kind] = {
                "requests": int(row["Request Count"]),
                "failures": int(row["Failure Count"]),
                "median_ms": float(row["Median Response Time"]),
                "p95_ms": float(row["95%"]),
                "p99_ms": float(row["99%"]),
                "requests_per_second": float(row["Requests/s"]),
            }
    return found


def _run_locust(url: str, client_file: Path, clients: int, seconds: int, prefix: Path) -> dict[str, dict]:
    command = [
        sys.executable, "-m", "locust",
        "-f", str(LOCUSTFILE),
        "--headless", "--only-summary",
        "-u", str(clients), "-r", str(clients),
        "-t", f"{seconds}s",
        "--host", url,
        "--csv", str(prefix),
        "--loglevel", "WARNING",
    ]
    environment = {**_child_environment(), "WEB_LOGIN_CLIENT_FILE": str(client_file)}
    # Locust exits with 1 when any request failed; the failures are recorded from its CSV.
    finished = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=seconds + 120)
    stats = prefix.with_name(prefix.name + "_stats.csv")
    if not stats.is_file():
        raise RuntimeError(f"locust wrote no statistics (exit {finished.returncode}): {finished.stderr[-500:]}")
    return parse_locust_stats(stats)


def _child_environment() -> dict:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    return environment


def run_web_load(settings: dict, supp, raw_dir: Path, results_dir: Path) -> int:
    cfg = supp.main
    passwords = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
    baselines = supp.baselines()
    path = raw_dir / "web_login.jsonl"
    error_path = raw_dir / "errors.jsonl"
    reset_file(path)
    drop_experiment(error_path, "web_login")
    log_line(results_dir, "Web login load test started (optional; config/web_login.yaml).")
    failures = 0
    algorithms = list(settings["algorithms"])
    with tempfile.TemporaryDirectory(prefix="web-login-") as temporary:
        folder = Path(temporary)
        for position, algorithm in enumerate(algorithms, start=1):
            params = baselines[algorithm]
            config_id = make_config_id(algorithm, params)
            server = None
            try:
                hasher = make_hasher(algorithm, params)
                users = [
                    {
                        "username": f"user{item.password_id:03d}",
                        "password": item.password,
                        "wrong_password": wrong_variant(item.password, cfg.charset),
                    }
                    for item in passwords
                ]
                stored = {user["username"]: hasher.hash_password(user["password"]) for user in users}
                server_file = folder / f"{algorithm}_server.json"
                client_file = folder / f"{algorithm}_client.json"
                server_file.write_text(json.dumps({"algorithm": algorithm, "params": params, "stored": stored}), encoding="utf-8")
                client_file.write_text(
                    json.dumps({"users": users, "wrong_password_fraction": float(settings["wrong_password_fraction"])}),
                    encoding="utf-8",
                )
                port = _free_port()
                url = f"http://127.0.0.1:{port}"
                server = subprocess.Popen(
                    [
                        sys.executable, "-m", "uvicorn", "password_benchmark.web_app:app_from_env", "--factory",
                        "--host", "127.0.0.1", "--port", str(port),
                        "--workers", str(int(settings["server_workers"])),
                        "--log-level", "warning", "--no-access-log",
                    ],
                    cwd=ROOT,
                    env={**_child_environment(), "WEB_LOGIN_SERVER_FILE": str(server_file)},
                )
                _wait_until_ready(url, server)
                for index in range(int(settings["warmup_requests"])):
                    user = users[index % len(users)]
                    if _post_login(url, user["username"], user["password"]) != 200:
                        raise RuntimeError("Warm-up login was rejected")
                for clients in settings["clients"]:
                    log_line(results_dir, f"[{position}/{len(algorithms)}] {config_id}: {clients} clients for {settings['duration_seconds']} s")
                    stats = _run_locust(
                        url, client_file, int(clients), int(settings["duration_seconds"]), folder / f"{algorithm}_{clients}"
                    )
                    for kind, values in stats.items():
                        append_jsonl(
                            path,
                            {
                                "algorithm": algorithm,
                                "clients": int(clients),
                                "config_id": config_id,
                                "config_sha256": settings["sha256"],
                                "duration_seconds": int(settings["duration_seconds"]),
                                "experiment": "web_login",
                                "kind": kind,
                                "params": params,
                                "server_workers": int(settings["server_workers"]),
                                **values,
                            },
                        )
            except Exception as exc:
                failures += 1
                append_jsonl(
                    error_path,
                    {"config_id": config_id, "error": f"{type(exc).__name__}: {exc}", "experiment": "web_login", "traceback": traceback.format_exc()},
                )
                log_line(results_dir, f"FAILED {config_id}: {type(exc).__name__}: {exc}")
            finally:
                if server is not None:
                    server.terminate()
                    try:
                        server.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        server.kill()
    log_line(results_dir, f"Web login load test finished. Failed configurations: {failures}.")
    return failures


def analyze_web_load(settings: dict, main_cfg, raw_dir: Path, results_dir: Path) -> int:
    rows = read_jsonl(raw_dir / "web_login.jsonl")
    if not rows:
        print("No web login measurements to analyze.", flush=True)
        return 1
    by_key = {(row["config_id"], row["clients"], row["kind"]): row for row in rows}
    table = []
    for config_id, clients in dict.fromkeys((row["config_id"], row["clients"]) for row in rows):
        correct = by_key.get((config_id, clients, "correct"))
        total = by_key.get((config_id, clients, "all"))
        if correct is None or total is None:
            continue
        table.append(
            {
                "algorithm": correct["algorithm"],
                "config_id": config_id,
                "clients": clients,
                "requests": total["requests"],
                "failures": total["failures"],
                "logins_per_second": total["requests_per_second"],
                "correct_median_ms": correct["median_ms"],
                "correct_p95_ms": correct["p95_ms"],
                "correct_p99_ms": correct["p99_ms"],
            }
        )
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(results_dir / "web_login.csv", table, list(table[0]) if table else [])

    reference = main_cfg.reference_workers
    md_rows = []
    for row in table:
        orientation = ""
        if row["clients"] == reference:
            inside = row["correct_p95_ms"] <= main_cfg.budget_a_ms and row["logins_per_second"] >= main_cfg.throughput_min
            orientation = "yes" if inside else "no"
        md_rows.append(
            [
                display_name(row["algorithm"]),
                str(row["clients"]),
                _fmt(row["logins_per_second"], 1),
                _fmt(row["correct_median_ms"], 0),
                _fmt(row["correct_p95_ms"], 0),
                f"{row['failures']} of {row['requests']}",
                orientation,
            ]
        )
    sample = rows[0]
    lines = [
        "# Optional: end-to-end login load test",
        "",
        f"Declared in config/web_login.yaml on {settings['declared']}, after both final runs (SHA-256 {sample['config_sha256']}). "
        "It is not part of the registered or supplementary designs and does not change their answers.",
        "",
        f"A FastAPI service with one process ({sample['server_workers']} worker) verifies POST /login requests against "
        "hashes of the synthetic corpus at each baseline. Locust clients on the same machine send requests with no wait "
        f"for {sample['duration_seconds']} s per row; {settings['wrong_password_fraction']:.0%} of requests use a wrong "
        "password of the same length and must return 401. A failure is any other status code.",
        "",
        _md_table(
            ["Algorithm", "Clients", "Logins/s", "Correct median ms", "Correct p95 ms", "Failures", f"Budget A thresholds at {reference}"],
            md_rows,
        ),
        "",
        f"The last column applies budget A's thresholds (p95 at most {main_cfg.budget_a_ms:g} ms, at least "
        f"{main_cfg.throughput_min:g} per second) to the {reference}-client row for orientation only. Research question 3 "
        "is answered by the registered concurrency experiment.",
        "",
        "Compared with the registered concurrency experiment, each request here also pays for HTTP, JSON parsing, and "
        "FastAPI's thread pool, and the locust clients use CPU on the same machine. Locust rounds response times above "
        "100 ms to two significant digits, so the percentiles are coarser than in the other tables.",
        "",
        "The benchmark uses synthetic passwords only. It does not perform password guessing against the service.",
        "",
    ]
    (results_dir / "web_login.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {results_dir / 'web_login.md'}", flush=True)
    return 0
