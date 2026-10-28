# Supplementary results

These experiments were declared in config/supplementary.yaml after the proposal and after the first registered runs were inspected (SHA-256 0e77f628553754344263bb8305d8c5b31a93d16917fbd4f0cdcfae4742fd3f11). They extend the registered experiment. The answers to the three research questions, and budgets A and B, are in results/summary.md and are not changed here.

Machine, library versions, and the registered rules are in results/summary.md and results/environment.json. Every measurement below comes from the same run and machine.

## S1. scrypt as a fourth algorithm

scrypt (hashlib.scrypt, OpenSSL) was added after the proposal. Its baseline follows the OWASP minimum: N=131072, r=8, p=1, which configures 128 MiB. The other rows are the registered baselines from the same run.

| Algorithm | Median ms | 95% CI | p95 ms | 95% CI | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 13.53 | 13.47 to 13.58 | 15.71 | 15.45 to 15.85 | 13.52 | 19.0 | 19.0 | 1000 |
| bcrypt | 41.78 | 41.72 to 41.83 | 43.66 | 43.42 to 43.94 | 41.76 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 48.27 | 48.19 to 48.32 | 49.23 | 49.15 to 49.30 | 48.24 | 0.0 |  | 1000 |
| scrypt | 199.96 | 199.63 to 200.17 | 205.49 | 204.94 to 205.86 | 199.93 | 128.1 | 128.0 | 1000 |

### Statistical tests

Kruskal-Wallis across the baselines: H = 3747.2, p < 0.0001, epsilon-squared = 0.937.

| Comparison | Median ratio | 95% CI | Mann-Whitney p (Holm) | Cliff's delta | Magnitude |
| --- | --- | --- | --- | --- | --- |
| Argon2id / bcrypt | 0.324 | 0.322 to 0.325 | < 0.0001 | -1.000 | large |
| Argon2id / PBKDF2-HMAC-SHA256 | 0.280 | 0.279 to 0.281 | < 0.0001 | -1.000 | large |
| Argon2id / scrypt | 0.068 | 0.067 to 0.068 | < 0.0001 | -1.000 | large |
| bcrypt / PBKDF2-HMAC-SHA256 | 0.866 | 0.864 to 0.867 | < 0.0001 | -0.997 | large |
| bcrypt / scrypt | 0.209 | 0.209 to 0.209 | < 0.0001 | -1.000 | large |
| PBKDF2-HMAC-SHA256 / scrypt | 0.241 | 0.241 to 0.242 | < 0.0001 | -1.000 | large |

The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a verification of the first algorithm is slower minus the probability that it is faster. With this many verifications a p-value detects even small differences, so the ratio and Cliff's delta describe the size. The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift within a configuration is not modeled.

For scrypt, raising n from 32768 to 262144 changed median verification latency from 46.74 ms (CI 46.67 to 46.80) to 400.57 ms (CI 400.17 to 400.87).

Concurrent verification at 4 thread-pool workers, judged by the registered budgets:

| Configuration | p95 ms | Per second | Memory MiB, 4 at once | Configured MiB x 4 | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- | --- |
| scrypt-n32768-r8-p1 | 56.29 | 74.4 | 128.2 | 128.0 | yes | yes |
| scrypt-n65536-r8-p1 | 107.16 | 37.6 | 256.2 | 256.0 | yes | yes |
| scrypt-n131072-r8-p1 | 223.70 | 18.2 | 512.3 | 512.0 | yes | yes |
| scrypt-n262144-r8-p1 | 442.79 | 9.1 | 1024.3 | 1024.0 | no | no |

- scrypt-n131072-r8-p1: thread pool 18.2/s, process pool 18.0/s, relative difference 1.0%, within the registered 15% agreement range.
  Per-verification median: thread pool 219.00 ms, process pool 211.81 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 1.1 ms, process pool 112.8 ms of 10975 ms and 2770 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 206.0 ms, process pool 296.7 ms.

## S2. Argon2id time cost

Memory stays at 19 MiB and parallelism at 1. Only t changes.

For Argon2id, raising time_cost from 1 to 4 changed median verification latency from 7.01 ms (CI 7.01 to 7.01) to 28.37 ms (CI 28.36 to 28.38).

| t | Median ms | 95% CI | p95 ms | CPU ms | RSS delta MiB | n |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 7.01 | 7.01 to 7.01 | 7.36 | 7.01 | 19.0 | 1000 |
| 2 | 14.15 | 14.14 to 14.16 | 15.40 | 14.15 | 19.0 | 1000 |
| 3 | 21.26 | 21.25 to 21.27 | 22.88 | 21.26 | 19.0 | 1000 |
| 4 | 28.37 | 28.36 to 28.38 | 30.15 | 28.37 | 19.0 | 1000 |

## S3. Tighter latency budgets

Same reference load (4 workers) and throughput minimum (10/s) as the registered budgets, with p95 limits of 100 ms, 250 ms. These limits are supplementary. The registered budgets A and B still answer research question 3.

Inside 100 ms: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, bcrypt-c10, bcrypt-c11, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000, scrypt-n32768-r8-p1 (9 of 18).
Inside 250 ms: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000, scrypt-n32768-r8-p1, scrypt-n65536-r8-p1, scrypt-n131072-r8-p1 (15 of 18).

| Configuration | p95 ms | Per second | 100 ms | 250 ms |
| --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 21.64 | 222.3 | yes | yes |
| argon2id-m32768-t2-p1 | 35.79 | 121.7 | yes | yes |
| argon2id-m47104-t2-p1 | 52.09 | 83.4 | yes | yes |
| argon2id-m65536-t2-p1 | 71.60 | 59.5 | yes | yes |
| argon2id-m131072-t2-p1 | 143.64 | 28.6 | no | yes |
| bcrypt-c10 | 51.31 | 83.6 | yes | yes |
| bcrypt-c11 | 96.14 | 43.4 | yes | yes |
| bcrypt-c12 | 187.92 | 21.8 | no | yes |
| bcrypt-c13 | 370.43 | 10.9 | no | no |
| bcrypt-c14 | 737.25 | 5.5 | no | no |
| pbkdf2-sha256-i600000 | 58.60 | 76.5 | yes | yes |
| pbkdf2-sha256-i900000 | 85.86 | 51.2 | yes | yes |
| pbkdf2-sha256-i1200000 | 120.42 | 38.3 | no | yes |
| pbkdf2-sha256-i1500000 | 136.96 | 31.4 | no | yes |
| scrypt-n32768-r8-p1 | 56.29 | 74.4 | yes | yes |
| scrypt-n65536-r8-p1 | 107.16 | 37.6 | no | yes |
| scrypt-n131072-r8-p1 | 223.70 | 18.2 | no | yes |
| scrypt-n262144-r8-p1 | 442.79 | 9.1 | no | no |

## S4. Concurrency beyond the core count

Thread-pool throughput at 1, 2, 4, 8, 16, 32 workers. The registered counts come from the registered phase and 16, 32 from the supplementary phase of the same run. This machine reports 12 logical CPUs.
The saturation point is the first worker count at which throughput rises by less than 10% over the previous count, or p95 exceeds 2 times the 1-worker p95.

| Configuration | 1 w/s | 2 w/s | 4 w/s | 8 w/s | 16 w/s | 32 w/s | Saturation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 67.4 | 117.3 | 222.3 | 396.3 | 466.3 | 457.4 | 16 |
| argon2id-m32768-t2-p1 | 37.1 | 63.6 | 121.7 | 215.5 | 263.1 | 260.6 | 16 |
| argon2id-m47104-t2-p1 | 24.1 | 43.9 | 83.4 | 150.5 | 174.5 | 173.3 | 16 |
| argon2id-m65536-t2-p1 | 16.7 | 30.9 | 59.5 | 107.5 | 124.7 | 119.3 | 16 |
| argon2id-m131072-t2-p1 | 8.0 | 15.1 | 28.6 | 51.6 | 60.2 | 54.2 | 16 |
| bcrypt-c10 | 22.5 | 43.7 | 83.6 | 163.3 | 201.1 | 173.9 | 16 |
| bcrypt-c11 | 11.5 | 22.4 | 43.4 | 81.9 | 102.8 | 106.7 | 32 |
| bcrypt-c12 | 5.9 | 11.3 | 21.8 | 42.1 | 53.3 | 54.8 | 32 |
| bcrypt-c13 | 3.0 | 5.7 | 10.9 | 21.2 | 27.2 | 27.2 | 32 |
| bcrypt-c14 | 1.5 | 2.8 | 5.5 | 10.6 | 13.6 | 13.7 | 32 |
| pbkdf2-sha256-i600000 | 20.2 | 39.5 | 76.5 | 144.2 | 174.5 | 177.3 | 16 |
| pbkdf2-sha256-i900000 | 13.3 | 26.4 | 51.2 | 98.9 | 116.3 | 119.6 | 16 |
| pbkdf2-sha256-i1200000 | 10.1 | 20.0 | 38.3 | 75.7 | 87.0 | 89.4 | 16 |
| pbkdf2-sha256-i1500000 | 8.2 | 16.0 | 31.4 | 59.3 | 68.5 | 70.1 | 16 |
| scrypt-n32768-r8-p1 | 19.9 | 37.6 | 74.4 | 144.7 | 174.7 | 171.0 | 16 |
| scrypt-n65536-r8-p1 | 9.5 | 18.7 | 37.6 | 72.7 | 86.7 | 87.3 | 32 |
| scrypt-n131072-r8-p1 | 4.8 | 9.3 | 18.2 | 34.1 | 41.5 | 36.2 | 16 |
| scrypt-n262144-r8-p1 | 2.4 | 4.7 | 9.1 | 17.6 | 19.6 | skipped | 16 |

Values are verifications per second. Per-worker p95 values are in s4_concurrency_all_workers.csv.
argon2id-m19456-t2-p1 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.
bcrypt-c10 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.
pbkdf2-sha256-i600000 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.
scrypt-n131072-r8-p1 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.

## S5. Equal verification time

Each algorithm was calibrated to the same target median verification time, then measured with the registered warmup and pilot rules and 10 repeats per password. bcrypt cost and scrypt N double the work per step, so those two use the nearest achievable step and can miss the target. The deviation column shows by how much.

| Target ms | Algorithm | Parameter | Median ms | 95% CI | Deviation | p95 ms | CPU ms | RSS delta MiB | Configured MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | Argon2id | memory_kib = 102 MiB | 97.09 | 96.90 to 97.25 | -2.9% | 102.29 | 97.08 | 102.0 | 102.0 |
| 100 | bcrypt | cost = 11 | 85.07 | 84.96 to 85.24 | -14.9% | 87.53 | 85.05 | 0.0 |  |
| 100 | PBKDF2-HMAC-SHA256 | iterations = 1260000 | 101.29 | 101.16 to 101.39 | +1.3% | 103.01 | 101.27 | 0.0 |  |
| 100 | scrypt | n = 65536 | 97.52 | 97.36 to 97.70 | -2.5% | 100.42 | 97.51 | 64.0 | 64.0 |
| 250 | Argon2id | memory_kib = 249 MiB | 247.26 | 247.09 to 247.49 | -1.1% | 252.16 | 247.24 | 249.0 | 249.0 |
| 250 | bcrypt | cost = 13 | 327.17 | 327.02 to 327.35 | +30.9% | 334.30 | 327.13 | 0.0 |  |
| 250 | PBKDF2-HMAC-SHA256 | iterations = 3200000 | 253.53 | 253.36 to 253.78 | +1.4% | 256.91 | 253.49 | 0.0 |  |
| 250 | scrypt | n = 131072 | 196.83 | 196.66 to 197.05 | -21.3% | 199.64 | 196.75 | 128.0 | 128.0 |

At about 100 ms per verification, measured peak memory growth was Argon2id 102.0 MiB; bcrypt 0.0 MiB; PBKDF2-HMAC-SHA256 0.0 MiB; scrypt 64.0 MiB.
At about 250 ms per verification, measured peak memory growth was Argon2id 249.0 MiB; bcrypt 0.0 MiB; PBKDF2-HMAC-SHA256 0.0 MiB; scrypt 128.0 MiB.
Equal time on this CPU does not mean equal cost for an attacker. Memory-hard algorithms also make each parallel guess hold memory, and this benchmark does not measure attacker hardware.

## S6. Wrong-password verification time

Correct and wrong passwords were verified in a seeded random interleaving at each baseline. The wrong password has the same length and differs only in its last character. The difference is the wrong-password median minus the correct-password median. The two are called equivalent when its 95% bootstrap interval lies within +/-2% of the correct median.

| Algorithm | Correct median ms | Wrong median ms | Difference ms | 95% CI | Equivalent | Mann-Whitney p | Cliff's delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 13.90 | 13.90 | -0.002 | -0.028 to +0.017 | yes | 0.3248 | -0.040 |
| bcrypt | 40.95 | 40.97 | +0.021 | -0.020 to +0.067 | yes | 0.1293 | +0.062 |
| PBKDF2-HMAC-SHA256 | 47.75 | 47.78 | +0.026 | -0.076 to +0.130 | yes | 0.9135 | -0.004 |
| scrypt | 195.92 | 196.17 | +0.248 | -0.042 to +0.451 | yes | 0.2199 | +0.050 |

Verification derives the full key for any input, so the derivation dominates the time. The PBKDF2 and scrypt wrappers compare the derived key with hmac.compare_digest; argon2-cffi and bcrypt compare inside the library. Timing at millisecond scale cannot resolve differences in the final comparison step, so this result does not by itself prove a constant-time comparison.

## S7. Input-handling pitfalls

Each pair was derived with the same salt and the baseline parameters. "same key" means both inputs would verify against one stored hash.

| Algorithm | sha256_of_64_bytes | sha256_of_65_bytes | sha256_of_100_bytes | trailing_nul |
| --- | --- | --- | --- | --- |
| Argon2id | different | different | different | different |
| bcrypt | different | different | rejected | different |
| PBKDF2-HMAC-SHA256 | different | same key | same key | same key |
| scrypt | different | same key | same key | same key |

Pairs that derived the same key: PBKDF2-HMAC-SHA256 sha256_of_65_bytes; PBKDF2-HMAC-SHA256 sha256_of_100_bytes; PBKDF2-HMAC-SHA256 trailing_nul; scrypt sha256_of_65_bytes; scrypt sha256_of_100_bytes; scrypt trailing_nul.
HMAC replaces a key longer than the 64-byte SHA-256 block with its digest and pads a shorter key with zero bytes. PBKDF2-HMAC-SHA256 uses the password as that key, and scrypt applies PBKDF2-HMAC-SHA256 to the password (RFC 7914). These are distinct byte strings that verify as the same password. They are not a weakness in guessing resistance, but an application that accepts raw bytes should normalize and bound passwords before hashing.
bcrypt sha256_of_100_bytes: ValueError: password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72]).
This experiment records input handling only. It does not test password guessing.
See the bcrypt input-length section of results/summary.md for the 72-byte and NUL cases.

## Scope

These are supplementary results for this machine, these library versions, and these configurations. They are not a universal ranking. The benchmark uses synthetic passwords only and does not perform password cracking.
