# Supplementary results

These experiments were declared in config/supplementary.yaml after the proposal and after the first registered runs were inspected (SHA-256 0e77f628553754344263bb8305d8c5b31a93d16917fbd4f0cdcfae4742fd3f11). They extend the registered experiment. The answers to the three research questions, and budgets A and B, are in results/summary.md and are not changed here.

Machine, library versions, and the registered rules are in results/summary.md and results/environment.json. Every measurement below comes from the same run and machine.

## S1. scrypt as a fourth algorithm

scrypt (hashlib.scrypt, OpenSSL) was added after the proposal. Its baseline follows the OWASP minimum: N=131072, r=8, p=1, which configures 128 MiB. The other rows are the registered baselines from the same run.

| Algorithm | Median ms | 95% CI | p95 ms | 95% CI | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 21.43 | 21.38 to 21.48 | 23.86 | 23.53 to 24.12 | 15.62 | 18.2 | 19.0 | 1000 |
| bcrypt | 46.35 | 46.32 to 46.38 | 47.09 | 47.01 to 47.20 | 46.88 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 207.64 | 207.52 to 207.74 | 211.74 | 211.08 to 212.93 | 203.12 | 0.0 |  | 1000 |
| scrypt | 488.38 | 487.97 to 488.64 | 497.45 | 495.78 to 498.51 | 484.38 | 127.2 | 128.0 | 1000 |

### Statistical tests

Kruskal-Wallis across the baselines: H = 3749.1, p < 0.0001, epsilon-squared = 0.938.

| Comparison | Median ratio | 95% CI | Mann-Whitney p (Holm) | Cliff's delta | Magnitude |
| --- | --- | --- | --- | --- | --- |
| Argon2id / bcrypt | 0.462 | 0.461 to 0.463 | < 0.0001 | -1.000 | large |
| Argon2id / PBKDF2-HMAC-SHA256 | 0.103 | 0.103 to 0.103 | < 0.0001 | -1.000 | large |
| Argon2id / scrypt | 0.044 | 0.044 to 0.044 | < 0.0001 | -1.000 | large |
| bcrypt / PBKDF2-HMAC-SHA256 | 0.223 | 0.223 to 0.223 | < 0.0001 | -1.000 | large |
| bcrypt / scrypt | 0.095 | 0.095 to 0.095 | < 0.0001 | -1.000 | large |
| PBKDF2-HMAC-SHA256 / scrypt | 0.425 | 0.425 to 0.426 | < 0.0001 | -1.000 | large |

The median ratio is the first algorithm's median divided by the second's. Cliff's delta is the probability that a verification of the first algorithm is slower minus the probability that it is faster. With this many verifications a p-value detects even small differences, so the ratio and Cliff's delta describe the size. The bootstrap treats verifications as exchangeable. Repeats of the same password ran in sequence, so slow drift within a configuration is not modeled.

For scrypt, raising n from 32768 to 262144 changed median verification latency from 121.25 ms (CI 121.16 to 121.36) to 993.59 ms (CI 992.27 to 994.82).

Concurrent verification at 4 thread-pool workers, judged by the registered budgets:

| Configuration | p95 ms | Per second | Memory MiB, 4 at once | Configured MiB x 4 | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- | --- |
| scrypt-n32768-r8-p1 | 157.87 | 27.5 | 127.3 | 128.0 | yes | yes |
| scrypt-n65536-r8-p1 | 298.25 | 13.9 | 255.3 | 256.0 | yes | yes |
| scrypt-n131072-r8-p1 | 587.64 | 7.0 | 511.3 | 512.0 | no | no |
| scrypt-n262144-r8-p1 | 1186.17 | 3.4 | 1023.3 | 1024.0 | no | no |

- scrypt-n131072-r8-p1: thread pool 7.0/s, process pool 6.4/s, relative difference 8.3%, within the registered 15% agreement range.
  Per-verification median: thread pool 567.90 ms, process pool 572.64 ms. Batch time not explained by verification work (batch wall time minus summed verification time / workers): thread pool 159.3 ms, process pool 210.3 ms of 28700 ms and 7824 ms batches.
  Worker startup, completed before the clock started and including the warm-up tasks: thread pool 201.5 ms, process pool 488.0 ms.

## S2. Argon2id time cost

Memory stays at 19 MiB and parallelism at 1. Only t changes.

For Argon2id, raising time_cost from 1 to 4 changed median verification latency from 13.19 ms (CI 13.12 to 13.26) to 39.82 ms (CI 39.73 to 39.91).

| t | Median ms | 95% CI | p95 ms | CPU ms | RSS delta MiB | n |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 13.19 | 13.12 to 13.26 | 14.46 | 15.62 | 18.2 | 1000 |
| 2 | 22.28 | 22.21 to 22.36 | 24.13 | 15.62 | 18.2 | 1000 |
| 3 | 31.17 | 31.06 to 31.30 | 33.33 | 31.25 | 18.2 | 1000 |
| 4 | 39.82 | 39.73 to 39.91 | 42.49 | 46.88 | 18.2 | 1000 |

## S3. Tighter latency budgets

Same reference load (4 workers) and throughput minimum (10/s) as the registered budgets, with p95 limits of 100 ms, 250 ms. These limits are supplementary. The registered budgets A and B still answer research question 3.

Inside 100 ms: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, bcrypt-c10 (3 of 18).
Inside 250 ms: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, scrypt-n32768-r8-p1 (8 of 18).

| Configuration | p95 ms | Per second | 100 ms | 250 ms |
| --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 45.43 | 110.1 | yes | yes |
| argon2id-m32768-t2-p1 | 74.82 | 61.6 | yes | yes |
| argon2id-m47104-t2-p1 | 104.70 | 42.6 | no | yes |
| argon2id-m65536-t2-p1 | 149.29 | 30.8 | no | yes |
| argon2id-m131072-t2-p1 | 284.92 | 15.0 | no | no |
| bcrypt-c10 | 62.69 | 74.1 | yes | yes |
| bcrypt-c11 | 111.04 | 38.5 | no | yes |
| bcrypt-c12 | 214.45 | 19.5 | no | yes |
| bcrypt-c13 | 445.70 | 9.1 | no | no |
| bcrypt-c14 | 821.30 | 4.9 | no | no |
| pbkdf2-sha256-i600000 | 274.29 | 16.1 | no | no |
| pbkdf2-sha256-i900000 | 389.40 | 10.8 | no | no |
| pbkdf2-sha256-i1200000 | 519.79 | 8.1 | no | no |
| pbkdf2-sha256-i1500000 | 634.49 | 6.5 | no | no |
| scrypt-n32768-r8-p1 | 157.87 | 27.5 | no | yes |
| scrypt-n65536-r8-p1 | 298.25 | 13.9 | no | no |
| scrypt-n131072-r8-p1 | 587.64 | 7.0 | no | no |
| scrypt-n262144-r8-p1 | 1186.17 | 3.4 | no | no |

## S4. Concurrency beyond the core count

Thread-pool throughput at 1, 2, 4, 8, 16, 32 workers. The registered counts come from the registered phase and 16, 32 from the supplementary phase of the same run. This machine reports 16 logical CPUs.
The saturation point is the first worker count at which throughput rises by less than 10% over the previous count, or p95 exceeds 2 times the 1-worker p95.

| Configuration | 1 w/s | 2 w/s | 4 w/s | 8 w/s | 16 w/s | 32 w/s | Saturation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 35.0 | 62.3 | 110.1 | 152.4 | 187.8 | 192.4 | 16 |
| argon2id-m32768-t2-p1 | 20.8 | 39.5 | 61.6 | 91.0 | 110.1 | 110.0 | 16 |
| argon2id-m47104-t2-p1 | 15.3 | 26.8 | 42.6 | 62.3 | 77.9 | 78.7 | 8 |
| argon2id-m65536-t2-p1 | 10.6 | 19.2 | 30.8 | 44.7 | 55.2 | 55.4 | 8 |
| argon2id-m131072-t2-p1 | 5.4 | 9.5 | 15.0 | 21.8 | 27.4 | 26.7 | 8 |
| bcrypt-c10 | 20.3 | 38.9 | 74.1 | 135.2 | 213.0 | 241.5 | 32 |
| bcrypt-c11 | 10.2 | 20.0 | 38.5 | 69.8 | 118.2 | 124.7 | 32 |
| bcrypt-c12 | 5.1 | 10.1 | 19.5 | 35.4 | 61.0 | 63.6 | 32 |
| bcrypt-c13 | 2.6 | 4.7 | 9.1 | 17.8 | 29.8 | 31.1 | 32 |
| bcrypt-c14 | 1.3 | 2.6 | 4.9 | 8.9 | 15.2 | 15.7 | 32 |
| pbkdf2-sha256-i600000 | 4.5 | 8.5 | 16.1 | 23.5 | 26.8 | 27.5 | 16 |
| pbkdf2-sha256-i900000 | 3.0 | 5.8 | 10.8 | 16.1 | 18.1 | 18.4 | 16 |
| pbkdf2-sha256-i1200000 | 2.2 | 4.3 | 8.1 | 12.1 | 13.2 | 13.7 | 16 |
| pbkdf2-sha256-i1500000 | 1.8 | 3.4 | 6.5 | 9.7 | 10.5 | 10.9 | 16 |
| scrypt-n32768-r8-p1 | 7.7 | 14.5 | 27.5 | 42.5 | 56.5 | 61.1 | 16 |
| scrypt-n65536-r8-p1 | 3.6 | 7.4 | 13.9 | 21.9 | 28.2 | 29.1 | 16 |
| scrypt-n131072-r8-p1 | 1.9 | 3.7 | 7.0 | 10.7 | 14.3 | 14.5 | 16 |
| scrypt-n262144-r8-p1 | 1.0 | 1.9 | 3.4 | 5.4 | 7.1 | 7.3 | 16 |

Values are verifications per second. Per-worker p95 values are in s4_concurrency_all_workers.csv.
argon2id-m19456-t2-p1 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.
bcrypt-c10 saturates at 32 workers: p95 exceeded 2x the 1-worker p95.
pbkdf2-sha256-i600000 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.
scrypt-n131072-r8-p1 saturates at 16 workers: p95 exceeded 2x the 1-worker p95.

## S5. Equal verification time

Each algorithm was calibrated to the same target median verification time, then measured with the registered warmup and pilot rules and 10 repeats per password. bcrypt cost and scrypt N double the work per step, so those two use the nearest achievable step and can miss the target. The deviation column shows by how much.

| Target ms | Algorithm | Parameter | Median ms | 95% CI | Deviation | p95 ms | CPU ms | RSS delta MiB | Configured MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | Argon2id | memory_kib = 72 MiB | 94.64 | 94.51 to 94.77 | -5.4% | 106.23 | 93.75 | 71.2 | 72.0 |
| 100 | bcrypt | cost = 11 | 93.10 | 93.06 to 93.16 | -6.9% | 94.91 | 93.75 | 0.0 |  |
| 100 | PBKDF2-HMAC-SHA256 | iterations = 270000 | 97.81 | 97.67 to 97.92 | -2.2% | 100.71 | 93.75 | 0.0 |  |
| 100 | scrypt | n = 32768 | 121.06 | 120.86 to 121.23 | +21.1% | 125.09 | 125.00 | 31.2 | 32.0 |
| 250 | Argon2id | memory_kib = 183 MiB | 253.47 | 253.04 to 253.97 | +1.4% | 266.28 | 250.00 | 182.2 | 183.0 |
| 250 | bcrypt | cost = 12 | 184.99 | 184.94 to 185.07 | -26.0% | 188.25 | 187.50 | 0.0 |  |
| 250 | PBKDF2-HMAC-SHA256 | iterations = 680000 | 240.38 | 240.13 to 240.78 | -3.8% | 248.33 | 234.38 | 0.0 |  |
| 250 | scrypt | n = 65536 | 244.85 | 244.53 to 245.25 | -2.1% | 250.81 | 250.00 | 63.2 | 64.0 |

At about 100 ms per verification, measured peak memory growth was Argon2id 71.2 MiB; bcrypt 0.0 MiB; PBKDF2-HMAC-SHA256 0.0 MiB; scrypt 31.2 MiB.
At about 250 ms per verification, measured peak memory growth was Argon2id 182.2 MiB; bcrypt 0.0 MiB; PBKDF2-HMAC-SHA256 0.0 MiB; scrypt 63.2 MiB.
Equal time on this CPU does not mean equal cost for an attacker. Memory-hard algorithms also make each parallel guess hold memory, and this benchmark does not measure attacker hardware.

## S6. Wrong-password verification time

Correct and wrong passwords were verified in a seeded random interleaving at each baseline. The wrong password has the same length and differs only in its last character. The difference is the wrong-password median minus the correct-password median. The two are called equivalent when its 95% bootstrap interval lies within +/-2% of the correct median.

| Algorithm | Correct median ms | Wrong median ms | Difference ms | 95% CI | Equivalent | Mann-Whitney p | Cliff's delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 21.75 | 21.83 | +0.082 | -0.001 to +0.143 | yes | 0.1478 | +0.059 |
| bcrypt | 46.32 | 46.33 | +0.010 | -0.040 to +0.042 | yes | 0.9398 | -0.003 |
| PBKDF2-HMAC-SHA256 | 213.76 | 213.66 | -0.103 | -0.338 to +0.130 | yes | 0.5368 | -0.025 |
| scrypt | 488.97 | 489.58 | +0.607 | -0.156 to +1.225 | yes | 0.1151 | +0.064 |

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
