# Results summary

## Machine

- Python: 3.13.5 (main, Jun 11 2025, 15:36:57) [Clang 16.0.0 (clang-1600.0.26.6)]
- OpenSSL: OpenSSL 3.5.1 1 Jul 2025
- CPU: Apple M4 Pro (12 physical cores, 12 logical)
- RAM: 24.0 GiB
- Platform: macOS-15.2-arm64-arm-64bit-Mach-O
- Power scheme: Battery Power: Sleep On Power Button 1 powermode 0 standby 1 ttyskeepawake 1 hibernatemode 3 powernap 1 hibernatefile /var/vm/sleepimage displaysleep 10 womp 0 networkoversleep 0 sleep 1 lessbright 1 tcpkeepalive 1 disksleep 10 AC Power: Sleep On Power Button 1 powermode 0 standby 1 ttyskeepawake 1 hibernatemode 3 powernap 1 hibernatefile /var/vm/sleepimage displaysleep 15 womp 1 networkoversleep 0 sleep 1 tcpkeepalive 1 disksleep 10
- Libraries: argon2-cffi 25.1.0, bcrypt 5.0.0, psutil 7.2.2, pandas 3.1.0, numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2, PyYAML 6.0.3
- Config SHA-256: fed42fd6b7c6f09c0870817614bc1d841c6766f99437cbfda8932e9047045aa4
- The full package list is in environment.json.

## Registered rules

Warmup verifications discarded per configuration: 10. Pilot verifications: 5. Measured repeats per password: 25, or 10 when the pilot median exceeds 2000 ms.
Budget A requires p95 latency at or below 500 ms and throughput of at least 10 verifications per second at 4 concurrent workers. Budget B uses the same throughput rule and a p95 limit of 1000 ms. Both conditions are required.
Verification time excludes salt generation and hash construction. Those happen before the timed calls.
Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.

## Research question 1

Under the baseline configurations, median verification latency was Argon2id 13.53 ms (95% CI 13.47 to 13.58; p95 15.71 ms, CPU 13.52 ms); bcrypt 41.78 ms (95% CI 41.72 to 41.83; p95 43.66 ms, CPU 41.76 ms); PBKDF2-HMAC-SHA256 48.27 ms (95% CI 48.19 to 48.32; p95 49.23 ms, CPU 48.24 ms).

| Algorithm | Median ms | 95% CI | p95 ms | 95% CI | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 13.53 | 13.47 to 13.58 | 15.71 | 15.45 to 15.85 | 13.52 | 19.0 | 19.0 | 1000 |
| bcrypt | 41.78 | 41.72 to 41.83 | 43.66 | 43.42 to 43.94 | 41.76 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 48.27 | 48.19 to 48.32 | 49.23 | 49.15 to 49.30 | 48.24 | 0.0 |  | 1000 |

### Statistical tests

Kruskal-Wallis across the baselines: H = 2662.4, p < 0.0001, epsilon-squared = 0.888.

| Comparison | Median ratio | 95% CI | Mann-Whitney p (Holm) | Cliff's delta | Magnitude |
| --- | --- | --- | --- | --- | --- |
| Argon2id / bcrypt | 0.324 | 0.322 to 0.325 | < 0.0001 | -1.000 | large |
| Argon2id / PBKDF2-HMAC-SHA256 | 0.280 | 0.279 to 0.281 | < 0.0001 | -1.000 | large |
| bcrypt / PBKDF2-HMAC-SHA256 | 0.866 | 0.864 to 0.867 | < 0.0001 | -0.997 | large |

The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a verification of the first algorithm is slower minus the probability that it is faster. With this many verifications a p-value detects even small differences, so the ratio and Cliff's delta describe the size. The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift within a configuration is not modeled.

## Research question 2

For Argon2id, raising memory_kib from 19 MiB to 128 MiB changed median verification latency from 13.53 ms (CI 13.47 to 13.58) to 121.05 ms (CI 120.96 to 121.11).
For bcrypt, raising cost from 10 to 14 changed median verification latency from 41.78 ms (CI 41.72 to 41.83) to 659.27 ms (CI 658.96 to 659.67).
For PBKDF2-HMAC-SHA256, raising iterations from 600000 to 1500000 changed median verification latency from 48.27 ms (CI 48.19 to 48.32) to 120.35 ms (CI 120.27 to 120.51).

Intervals for every sweep point are in rq2_parameter_sweep.csv (95% bootstrap).

## Research question 3

At 4 concurrent thread-pool verifications, configurations inside budget A: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, bcrypt-c13, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000.
Inside budget B but outside budget A: none.
Outside both budgets: bcrypt-c14.

| Configuration | p95 ms | Per second | Memory MiB, 4 at once | Configured MiB x 4 | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 21.64 | 222.3 | 76.0 | 76.0 | yes | yes |
| argon2id-m32768-t2-p1 | 35.79 | 121.7 | 128.0 | 128.0 | yes | yes |
| argon2id-m47104-t2-p1 | 52.09 | 83.4 | 184.0 | 184.0 | yes | yes |
| argon2id-m65536-t2-p1 | 71.60 | 59.5 | 256.0 | 256.0 | yes | yes |
| argon2id-m131072-t2-p1 | 143.64 | 28.6 | 512.0 | 512.0 | yes | yes |
| bcrypt-c10 | 51.31 | 83.6 | 0.0 |  | yes | yes |
| bcrypt-c11 | 96.14 | 43.4 | 0.0 |  | yes | yes |
| bcrypt-c12 | 187.92 | 21.8 | 0.0 |  | yes | yes |
| bcrypt-c13 | 370.43 | 10.9 | 0.1 |  | yes | yes |
| bcrypt-c14 | 737.25 | 5.5 | 0.0 |  | no | no |
| pbkdf2-sha256-i600000 | 58.60 | 76.5 | 0.0 |  | yes | yes |
| pbkdf2-sha256-i900000 | 85.86 | 51.2 | 0.0 |  | yes | yes |
| pbkdf2-sha256-i1200000 | 120.42 | 38.3 | 0.0 |  | yes | yes |
| pbkdf2-sha256-i1500000 | 136.96 | 31.4 | 0.0 |  | yes | yes |

The memory column is the median peak growth of a fresh process while 4 verifications ran at once (rq3_concurrent_memory.csv). It is measured separately from the throughput batches. The throughput batches reuse one process, so their process-tree RSS (shared_process_peak_rss_mib in rq3_concurrency.csv) includes memory retained from earlier configurations and is not an isolated measurement.

### Process-pool check

- argon2id-m19456-t2-p1: thread pool 222.3/s, process pool 216.5/s, relative difference 2.6%, within the registered 15% agreement range.
  Per-verification median: thread pool 17.16 ms, process pool 16.74 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 9.0 ms, process pool 19.8 ms of 900 ms and 231 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 217.1 ms, process pool 270.7 ms.
- bcrypt-c10: thread pool 83.6/s, process pool 82.7/s, relative difference 1.0%, within the registered 15% agreement range.
  Per-verification median: thread pool 46.49 ms, process pool 45.72 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 17.4 ms, process pool 33.6 ms of 2394 ms and 604 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 207.0 ms, process pool 267.5 ms.
- pbkdf2-sha256-i600000: thread pool 76.5/s, process pool 77.3/s, relative difference 1.0%, within the registered 15% agreement range.
  Per-verification median: thread pool 50.00 ms, process pool 49.19 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 24.6 ms, process pool 31.3 ms of 2615 ms and 647 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 205.2 ms, process pool 281.3 ms.

## bcrypt input length

Library bcrypt 5.0.0, cost 10.

The selected bcrypt library rejected every password longer than 72 bytes before hashing (ValueError: password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])). It did not silently keep only the first 72 bytes.
A password containing a NUL byte did not match the shorter prefix that ends at that NUL, so the library kept the bytes after the NUL.
Changing only the bytes after that NUL produced a different verification result.
This library enforces the 72-byte limit by rejecting the input. Application code should still impose the same limit so the user receives a clear validation error. This experiment records input handling only. It does not test password guessing.

| Case | Bytes | Self | First 72 bytes | Alternate | Stops at NUL |
| --- | --- | --- | --- | --- | --- |
| ascii_71 | 71 | true |  |  |  |
| ascii_72 | 72 | true |  |  |  |
| ascii_73 | 73 | rejected | rejected | rejected | rejected |
| ascii_100 | 100 | rejected | rejected | rejected | rejected |
| prefix72_pair | 76 | rejected | rejected | rejected | rejected |
| utf8_boundary | 73 | rejected | rejected | rejected | rejected |
| nul_inside_first_72 | 31 | true |  | false | false |

## Appendix: hash construction

These times are not part of the verification comparison. Hash construction was excluded from the timed verification calls.

| Configuration | Median hash ms | n |
| --- | --- | --- |
| argon2id-m19456-t2-p1 | 13.28 | 40 |
| argon2id-m32768-t2-p1 | 25.51 | 40 |
| argon2id-m47104-t2-p1 | 38.85 | 40 |
| argon2id-m65536-t2-p1 | 57.18 | 40 |
| argon2id-m131072-t2-p1 | 125.62 | 40 |
| bcrypt-c10 | 41.90 | 40 |
| bcrypt-c11 | 83.68 | 40 |
| bcrypt-c12 | 165.67 | 40 |
| bcrypt-c13 | 328.46 | 40 |
| bcrypt-c14 | 659.21 | 40 |
| pbkdf2-sha256-i600000 | 47.72 | 40 |
| pbkdf2-sha256-i900000 | 72.63 | 40 |
| pbkdf2-sha256-i1200000 | 96.60 | 40 |
| pbkdf2-sha256-i1500000 | 120.61 | 40 |

## Scope

These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.
The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.
