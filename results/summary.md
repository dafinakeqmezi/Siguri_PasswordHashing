# Results summary

## Machine

- Python: 3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
- OpenSSL: OpenSSL 3.0.16 11 Feb 2025
- CPU: AMD Ryzen 7 PRO 6850U with Radeon Graphics (8 physical cores, 16 logical)
- RAM: 27.8 GiB
- Platform: Windows-11-10.0.26200-SP0
- Power scheme: Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e (Balanced)
- Libraries: argon2-cffi 25.1.0, bcrypt 5.0.0, psutil 7.2.2, pandas 3.1.0, numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2, PyYAML 6.0.3
- Config SHA-256: fed42fd6b7c6f09c0870817614bc1d841c6766f99437cbfda8932e9047045aa4
- The full package list is in environment.json.

## Registered rules

Warmup verifications discarded per configuration: 10. Pilot verifications: 5. Measured repeats per password: 25, or 10 when the pilot median exceeds 2000 ms.
Budget A requires p95 latency at or below 500 ms and throughput of at least 10 verifications per second at 4 concurrent workers. Budget B uses the same throughput rule and a p95 limit of 1000 ms. Both conditions are required.
Verification time excludes salt generation and hash construction. Those happen before the timed calls.
Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.

## Research question 1

Under the baseline configurations, median verification latency was Argon2id 21.43 ms (95% CI 21.38 to 21.48; p95 23.86 ms, CPU 15.62 ms); bcrypt 46.35 ms (95% CI 46.32 to 46.38; p95 47.09 ms, CPU 46.88 ms); PBKDF2-HMAC-SHA256 207.64 ms (95% CI 207.52 to 207.74; p95 211.74 ms, CPU 203.12 ms).

| Algorithm | Median ms | 95% CI | p95 ms | 95% CI | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 21.43 | 21.38 to 21.48 | 23.86 | 23.53 to 24.12 | 15.62 | 18.2 | 19.0 | 1000 |
| bcrypt | 46.35 | 46.32 to 46.38 | 47.09 | 47.01 to 47.20 | 46.88 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 207.64 | 207.52 to 207.74 | 211.74 | 211.08 to 212.93 | 203.12 | 0.0 |  | 1000 |

### Statistical tests

Kruskal-Wallis across the baselines: H = 2665.8, p < 0.0001, epsilon-squared = 0.889.

| Comparison | Median ratio | 95% CI | Mann-Whitney p (Holm) | Cliff's delta | Magnitude |
| --- | --- | --- | --- | --- | --- |
| Argon2id / bcrypt | 0.462 | 0.461 to 0.463 | < 0.0001 | -1.000 | large |
| Argon2id / PBKDF2-HMAC-SHA256 | 0.103 | 0.103 to 0.103 | < 0.0001 | -1.000 | large |
| bcrypt / PBKDF2-HMAC-SHA256 | 0.223 | 0.223 to 0.223 | < 0.0001 | -1.000 | large |

The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a verification of the first algorithm is slower minus the probability that it is faster. With this many verifications a p-value detects even small differences, so the ratio and Cliff's delta describe the size. The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift within a configuration is not modeled.

## Research question 2

For Argon2id, raising memory_kib from 19 MiB to 128 MiB changed median verification latency from 21.43 ms (CI 21.38 to 21.48) to 179.59 ms (CI 178.44 to 180.77).
For bcrypt, raising cost from 10 to 14 changed median verification latency from 46.35 ms (CI 46.32 to 46.38) to 737.26 ms (CI 737.11 to 737.47).
For PBKDF2-HMAC-SHA256, raising iterations from 600000 to 1500000 changed median verification latency from 207.64 ms (CI 207.52 to 207.74) to 518.15 ms (CI 517.98 to 518.34).

Intervals for every sweep point are in rq2_parameter_sweep.csv (95% bootstrap).

## Research question 3

At 4 concurrent thread-pool verifications, configurations inside budget A: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000.
Inside budget B but outside budget A: none.
Outside both budgets: bcrypt-c13, bcrypt-c14, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000.

| Configuration | p95 ms | Per second | Memory MiB, 4 at once | Configured MiB x 4 | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 45.43 | 110.1 | 75.3 | 76.0 | yes | yes |
| argon2id-m32768-t2-p1 | 74.82 | 61.6 | 127.3 | 128.0 | yes | yes |
| argon2id-m47104-t2-p1 | 104.70 | 42.6 | 183.3 | 184.0 | yes | yes |
| argon2id-m65536-t2-p1 | 149.29 | 30.8 | 255.3 | 256.0 | yes | yes |
| argon2id-m131072-t2-p1 | 284.92 | 15.0 | 511.3 | 512.0 | yes | yes |
| bcrypt-c10 | 62.69 | 74.1 | 0.0 |  | yes | yes |
| bcrypt-c11 | 111.04 | 38.5 | 0.0 |  | yes | yes |
| bcrypt-c12 | 214.45 | 19.5 | 0.0 |  | yes | yes |
| bcrypt-c13 | 445.70 | 9.1 | 0.0 |  | no | no |
| bcrypt-c14 | 821.30 | 4.9 | 0.0 |  | no | no |
| pbkdf2-sha256-i600000 | 274.29 | 16.1 | 0.0 |  | yes | yes |
| pbkdf2-sha256-i900000 | 389.40 | 10.8 | 0.0 |  | yes | yes |
| pbkdf2-sha256-i1200000 | 519.79 | 8.1 | 0.0 |  | no | no |
| pbkdf2-sha256-i1500000 | 634.49 | 6.5 | 0.0 |  | no | no |

The memory column is the median peak growth of a fresh process while 4 verifications ran at once (rq3_concurrent_memory.csv). It is measured separately from the throughput batches. The throughput batches reuse one process, so their process-tree RSS (shared_process_peak_rss_mib in rq3_concurrency.csv) includes memory retained from earlier configurations and is not an isolated measurement.

### Process-pool check

- argon2id-m19456-t2-p1: thread pool 110.1/s, process pool 115.3/s, relative difference 4.7%, within the registered 15% agreement range.
  Per-verification median: thread pool 34.98 ms, process pool 32.08 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 15.3 ms, process pool 26.8 ms of 1816 ms and 434 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 201.5 ms, process pool 463.1 ms.
- bcrypt-c10: thread pool 74.1/s, process pool 76.2/s, relative difference 2.9%, within the registered 15% agreement range.
  Per-verification median: thread pool 51.33 ms, process pool 49.43 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 23.1 ms, process pool 36.9 ms of 2701 ms and 656 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 201.2 ms, process pool 464.0 ms.
- pbkdf2-sha256-i600000: thread pool 16.1/s, process pool 13.3/s, relative difference 17.9%, outside the registered 15% agreement range.
  Per-verification median: thread pool 241.00 ms, process pool 281.06 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 108.9 ms, process pool 93.3 ms of 12386 ms and 3770 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 201.5 ms, process pool 465.3 ms.
  The difference is outside the registered range. It is reported as a finding and the measurement is kept.

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
| argon2id-m19456-t2-p1 | 21.79 | 40 |
| argon2id-m32768-t2-p1 | 41.37 | 40 |
| argon2id-m47104-t2-p1 | 61.94 | 40 |
| argon2id-m65536-t2-p1 | 85.18 | 40 |
| argon2id-m131072-t2-p1 | 178.77 | 40 |
| bcrypt-c10 | 46.33 | 40 |
| bcrypt-c11 | 92.51 | 40 |
| bcrypt-c12 | 184.98 | 40 |
| bcrypt-c13 | 368.95 | 40 |
| bcrypt-c14 | 736.47 | 40 |
| pbkdf2-sha256-i600000 | 207.95 | 40 |
| pbkdf2-sha256-i900000 | 312.02 | 40 |
| pbkdf2-sha256-i1200000 | 416.14 | 40 |
| pbkdf2-sha256-i1500000 | 518.10 | 40 |

## Scope

These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.
The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.
