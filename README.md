# Experimental Comparison of Password Hashing Algorithms

Semester project by Dafina Keqmezi, Delizë Kadriu, and Jeta Syla.

The benchmark compares Argon2id, bcrypt, and PBKDF2-HMAC-SHA256 through maintained libraries. It measures verification latency, CPU time, memory, and throughput. It also records how the selected bcrypt library treats passwords longer than 72 bytes. The algorithms are not implemented from scratch. The benchmark does not crack passwords and it uses only synthetic passwords.

## Research questions

1. How do the three algorithms compare in verification latency, CPU time, and memory at the baseline configurations?
2. How does raising the main cost parameter of each algorithm change verification performance and resource use?
3. Which configurations stay inside the registered latency budgets while keeping the registered throughput under concurrent verification?

## Registered design

`config/experiment.yaml` is the design. Do not change it after looking at results.

Baselines, from the OWASP Password Storage Cheat Sheet minima:

- Argon2id: 19 MiB (`m=19456` KiB), `t=2`, `p=1`
- bcrypt: cost 10
- PBKDF2-HMAC-SHA256: 600000 iterations

The sweep raises one parameter and keeps the others fixed:

- Argon2id memory: 19, 32, 46, 64, and 128 MiB
- bcrypt cost: 10, 11, 12, 13, and 14
- PBKDF2 iterations: 600000, 900000, 1200000, and 1500000

Forty synthetic ASCII passwords are generated from seed `20261023`, ten each of length 12, 16, 24, and 32 characters. The same corpus is used for every algorithm. Every password is at most 32 bytes, so the 72-byte bcrypt limit does not affect the latency comparison.

For each configuration the runner builds the hash before timing. It then discards 10 warmup verifications and 5 pilot verifications. The reported sample is 25 repeats of each password (1000 verifications). If the pilot median is above 2000 ms, that configuration uses 10 repeats (400 verifications) instead. The rule is applied automatically and marked `reduced n` on the figure.

Budget A is p95 latency at or below 500 ms and at least 10 verifications per second, at 4 concurrent workers. Budget B raises the latency limit to 1000 ms and keeps the same throughput rule. A configuration meets a budget only when both conditions hold. These are experimental login thresholds, not a claim that the configurations are equally secure.

Latency reported for the concurrent test is the wall time of `verify()` while the other workers are busy. Throughput is successful verifications divided by the wall time of the batch. The main concurrent measurements use a thread pool, because these libraries release the interpreter lock during the hash. Each baseline is also checked once with a process pool. The registered agreement range is 15 percent relative throughput.

Memory is the increase in the peak working set of a fresh process during one verification. Argon2id's configured memory is the meaningful memory setting. Growth of only a few MiB is measurement noise.

## Setup

Windows and macOS use the same benchmark and configuration. Python 3.12 is
recommended for consistency across the team; the local Mac run also used Python
3.13. Record the actual version with each run. Run commands from the project root.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Activation is optional: these commands call the virtual environment directly,
so PowerShell execution-policy changes are unnecessary.

### macOS (Terminal)

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-lock.txt
```

Use `python3.12` in the first command if you have it installed and want the same
Python version as teammates using `py -3.12` on Windows.

`requirements-lock.txt` pins package versions, not the OS, Python interpreter,
or OpenSSL. `requirements.txt` lists the direct libraries. Do not commit the
`.venv` directory or copy it between operating systems.

### Check and estimate

Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m password_benchmark smoke
.\.venv\Scripts\python.exe -m password_benchmark estimate
```

macOS:

```bash
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/python -m password_benchmark smoke
./.venv/bin/python -m password_benchmark estimate
```

`smoke` writes only to `data/smoke` and `results/smoke`. Those figures are a pipeline check. Do not put them in the report.

The estimate is rough and is not an experimental result.

## Full run

Collect the report numbers on one idle machine:

- connect the power adapter
- on Windows, select the High performance power scheme if available
- on macOS, disable Low Power Mode and keep the lid open; use the same power settings throughout the run
- close browsers and other heavy applications
- do not use the machine until the process exits

```powershell
.\.venv\Scripts\python.exe -m password_benchmark all
```

On macOS:

```bash
./.venv/bin/python -m password_benchmark all
```

The full run replaces the working `data/raw` measurements and generated results.
Before another run, save the completed run under a unique name:

```powershell
# Windows
.\.venv\Scripts\python.exe -m password_benchmark save-run windows-dafina-2026-10-28
```

```bash
# macOS
./.venv/bin/python -m password_benchmark save-run mac-delize-2026-10-28
```

This copies raw data, results, configuration, and the source as it exists at
save time into `runs/NAME`, with file checksums. It refuses to overwrite an
existing saved run. Save immediately after measurement, before editing source.
Share each machine's complete saved folder. The existing Windows and Mac runs
are preserved separately; see [runs/README.md](runs/README.md).

With no command, the program prints help and does not start a measurement.

Individual phases, if one of them has to be repeated:

```powershell
.\.venv\Scripts\python.exe -m password_benchmark environment
.\.venv\Scripts\python.exe -m password_benchmark bcrypt-length
.\.venv\Scripts\python.exe -m password_benchmark latency
.\.venv\Scripts\python.exe -m password_benchmark concurrent
.\.venv\Scripts\python.exe -m password_benchmark analyze
```

Repeating a phase replaces that phase's raw file. `analyze` can be repeated without repeating the measurements.
For any of these commands on macOS, replace `.\.venv\Scripts\python.exe` with
`./.venv/bin/python`.

## Output

| Path | Contents |
| --- | --- |
| `results/environment.json` | Hardware, operating system, Python, OpenSSL, library versions, power scheme |
| `results/summary.md` | Answers to the three research questions, with the tables |
| `results/rq1_baseline.csv` | Baseline median, p95, CPU, and memory |
| `results/rq2_parameter_sweep.csv` | One row per sweep configuration |
| `results/rq3_concurrency.csv` | Throughput and p95 at each worker count |
| `results/bcrypt_length.csv` | Observed bcrypt input handling |
| `results/figures/` | Figures for the report |
| `data/raw/*.jsonl` | One measurement per line |

`summary.md` is generated from the raw files. Copy the sentences and tables into the report, and keep the interpretation inside the limits stated at the bottom of that file.

## Method notes for the report

- One controlled machine. The results belong to the hardware and library versions in `environment.json`.
- All teammates can run the harness on Windows or macOS. Select one machine's complete run for the main comparison to retain the proposal's controlled-machine design. Additional machines can be reported separately as a supplementary experiment. Different hardware, OS, Python, and OpenSSL versions change together, so these runs cannot isolate an OS performance effect. Do not pool their samples.
- Windows records its CPU model and active power scheme; macOS records its chip model and `pmset` power settings. Apple Silicon CPU frequency is omitted because the available readings are unreliable.
- Sequential memory uses a fresh child process and OS peak counters: peak working set on Windows and `getrusage` maximum RSS on macOS. The delta is the increase in the process high-water mark, not an exact allocation count. Older Mac results collected before this correction retain their original measurement method.
- Concurrent RSS is total resident memory of the benchmark process tree. The runner reuses its main process between configurations, so retained allocations from earlier cases can inflate later readings. Do not interpret these values as each algorithm's isolated memory requirement.
- Password salts are random and are created during hash construction, outside the timed verification.
- `wall_ns` in the latency file is only the verification call. CPU time uses the process timer for the same call.
- Concurrent CPU time is the CPU time of the worker processes or threads over the whole batch, not a per-call timer. Per-call CPU timers are misleading when several verifications share a process.
- Argon2id parallelism stays at `p=1` in the sequential measurements. Extra math libraries are limited to one thread with `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `MKL_NUM_THREADS`.
- The bcrypt length experiment uses the baseline cost and the same library as the performance tests. It records whether the library hashes the input, rejects it, or treats two different byte strings as the same password. A refusal is a result, not a failed run. It is not a cracking test.

## Limitations

The findings apply only to this machine, these library versions, and these configurations. They should not be presented as a universal ranking. A faster verification on this CPU means each guess is cheaper on this CPU. It is not, by itself, a complete security comparison.

## References

- OWASP Cheat Sheet Series, Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- RFC 9106, Argon2
- The project proposal, "Experimental Comparison of Password Hashing Algorithms for Web Applications"
