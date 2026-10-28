# Results summary

## Machine

- Python: 3.13.5 (main, Jun 11 2025, 15:36:57) [Clang 16.0.0 (clang-1600.0.26.6)]
- OpenSSL: OpenSSL 3.5.1 1 Jul 2025
- CPU: Apple M4 Pro (12 physical cores, 12 logical)
- RAM: 24.0 GiB
- Platform: macOS-15.2-arm64-arm-64bit-Mach-O
- Power scheme: Battery Power: Sleep On Power Button 1 powermode 0 standby 1 ttyskeepawake 1 hibernatemode 3 powernap 1 hibernatefile /var/vm/sleepimage displaysleep 10 womp 0 networkoversleep 0 sleep 1 lessbright 1 tcpkeepalive 1 disksleep 10 AC Power: Sleep On Power Button 1 powermode 0 standby 1 ttyskeepawake 1 hibernatemode 3 powernap 1 hibernatefile /var/vm/sleepimage displaysleep 15 womp 1 networkoversleep 0 sleep 1 tcpkeepalive 1 disksleep 10
- Libraries: argon2-cffi 25.1.0, bcrypt 5.0.0, psutil 7.2.2, pandas 3.1.0, numpy 2.5.4, scipy not installed, matplotlib 3.11.2, PyYAML 6.0.3
- Config SHA-256: fed42fd6b7c6f09c0870817614bc1d841c6766f99437cbfda8932e9047045aa4
- The full package list is in environment.json.

## Registered rules

Warmup verifications discarded per configuration: 10. Pilot verifications: 5. Measured repeats per password: 25, or 10 when the pilot median exceeds 2000 ms.
Budget A requires p95 latency at or below 500 ms and throughput of at least 10 verifications per second at 4 concurrent workers. Budget B uses the same throughput rule and a p95 limit of 1000 ms. Both conditions are required.
Verification time excludes salt generation and hash construction. Those happen before the timed calls.
Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.

## Research question 1

Under the baseline configurations, median verification latency was Argon2id 12.86 ms (95% CI 12.85 to 12.87; p95 14.13 ms, CPU 12.86 ms); bcrypt 41.10 ms (95% CI 41.09 to 41.12; p95 42.80 ms, CPU 41.08 ms); PBKDF2-HMAC-SHA256 47.62 ms (95% CI 47.58 to 47.65; p95 48.54 ms, CPU 47.60 ms).

| Algorithm | Median ms | 95% CI | p95 ms | 95% CI | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 12.86 | 12.85 to 12.87 | 14.13 | 13.98 to 14.24 | 12.86 | 19.0 | 19.0 | 1000 |
| bcrypt | 41.10 | 41.09 to 41.12 | 42.80 | 42.54 to 42.98 | 41.08 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 47.62 | 47.58 to 47.65 | 48.54 | 48.46 to 48.59 | 47.60 | 0.0 |  | 1000 |

### Statistical tests

Kruskal-Wallis across the baselines: H = 2665.1, p < 0.0001, epsilon-squared = 0.889.

| Comparison | Median ratio | 95% CI | Mann-Whitney p (Holm) | Cliff's delta | Magnitude |
| --- | --- | --- | --- | --- | --- |
| Argon2id / bcrypt | 0.313 | 0.313 to 0.313 | < 0.0001 | -1.000 | large |
| Argon2id / PBKDF2-HMAC-SHA256 | 0.270 | 0.270 to 0.270 | < 0.0001 | -1.000 | large |
| bcrypt / PBKDF2-HMAC-SHA256 | 0.863 | 0.862 to 0.864 | < 0.0001 | -0.999 | large |

The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a verification of the first algorithm is slower minus the probability that it is faster. With this many verifications a p-value detects even small differences, so the ratio and Cliff's delta describe the size. The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift within a configuration is not modeled.

## Research question 2

For Argon2id, raising memory_kib from 19 MiB to 128 MiB changed median verification latency from 12.86 ms (CI 12.85 to 12.87) to 117.71 ms (CI 117.57 to 117.82).
For bcrypt, raising cost from 10 to 14 changed median verification latency from 41.10 ms (CI 41.09 to 41.12) to 657.86 ms (CI 657.67 to 658.05).
For PBKDF2-HMAC-SHA256, raising iterations from 600000 to 1500000 changed median verification latency from 47.62 ms (CI 47.58 to 47.65) to 120.67 ms (CI 120.60 to 120.74).

Intervals for every sweep point are in rq2_parameter_sweep.csv (95% bootstrap).

## Research question 3

At 4 concurrent thread-pool verifications, configurations inside budget A: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, bcrypt-c13, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000.
Inside budget B but outside budget A: none.
Outside both budgets: bcrypt-c14.

| Configuration | p95 ms | Per second | Memory MiB, 4 at once | Configured MiB x 4 | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 21.60 | 220.7 | 76.2 | 76.0 | yes | yes |
| argon2id-m32768-t2-p1 | 35.30 | 122.7 | 128.2 | 128.0 | yes | yes |
| argon2id-m47104-t2-p1 | 52.58 | 81.6 | 184.2 | 184.0 | yes | yes |
| argon2id-m65536-t2-p1 | 72.01 | 59.0 | 256.2 | 256.0 | yes | yes |
| argon2id-m131072-t2-p1 | 143.86 | 28.3 | 512.2 | 512.0 | yes | yes |
| bcrypt-c10 | 48.04 | 84.9 | 0.2 |  | yes | yes |
| bcrypt-c11 | 93.76 | 43.0 | 0.1 |  | yes | yes |
| bcrypt-c12 | 186.53 | 21.7 | 0.0 |  | yes | yes |
| bcrypt-c13 | 369.61 | 11.0 | 0.1 |  | yes | yes |
| bcrypt-c14 | 736.89 | 5.5 | 0.0 |  | no | no |
| pbkdf2-sha256-i600000 | 59.04 | 75.3 | 0.2 |  | yes | yes |
| pbkdf2-sha256-i900000 | 92.80 | 51.0 | 0.2 |  | yes | yes |
| pbkdf2-sha256-i1200000 | 118.88 | 38.1 | 0.2 |  | yes | yes |
| pbkdf2-sha256-i1500000 | 150.00 | 30.6 | 0.2 |  | yes | yes |

The memory column is the median peak growth of a fresh process while 4 verifications ran at once (rq3_concurrent_memory.csv). It is measured separately from the throughput batches. The throughput batches reuse one process, so their process-tree RSS (shared_process_peak_rss_mib in rq3_concurrency.csv) includes memory retained from earlier configurations and is not an isolated measurement.

### Process-pool check

- argon2id-m19456-t2-p1: thread pool 220.7/s, process pool 227.0/s, relative difference 2.8%, within the registered 15% agreement range.
  Per-verification median: thread pool 17.01 ms, process pool 16.37 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 14.8 ms, process pool 11.4 ms of 906 ms and 220 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 203.1 ms, process pool 285.9 ms.
- bcrypt-c10: thread pool 84.9/s, process pool 81.5/s, relative difference 4.0%, within the registered 15% agreement range.
  Per-verification median: thread pool 46.71 ms, process pool 46.43 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 7.9 ms, process pool 35.0 ms of 2356 ms and 614 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 205.2 ms, process pool 266.5 ms.
- pbkdf2-sha256-i600000: thread pool 75.3/s, process pool 76.1/s, relative difference 1.1%, within the registered 15% agreement range.
  Per-verification median: thread pool 50.42 ms, process pool 49.59 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 37.2 ms, process pool 37.1 ms of 2657 ms and 657 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 205.2 ms, process pool 255.6 ms.

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
| argon2id-m19456-t2-p1 | 12.92 | 40 |
| argon2id-m32768-t2-p1 | 26.16 | 40 |
| argon2id-m47104-t2-p1 | 37.46 | 40 |
| argon2id-m65536-t2-p1 | 54.58 | 40 |
| argon2id-m131072-t2-p1 | 116.76 | 40 |
| bcrypt-c10 | 41.12 | 40 |
| bcrypt-c11 | 82.04 | 40 |
| bcrypt-c12 | 164.09 | 40 |
| bcrypt-c13 | 327.95 | 40 |
| bcrypt-c14 | 657.81 | 40 |
| pbkdf2-sha256-i600000 | 47.74 | 40 |
| pbkdf2-sha256-i900000 | 71.55 | 40 |
| pbkdf2-sha256-i1200000 | 95.86 | 40 |
| pbkdf2-sha256-i1500000 | 120.72 | 40 |

## Scope

These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.
The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.
