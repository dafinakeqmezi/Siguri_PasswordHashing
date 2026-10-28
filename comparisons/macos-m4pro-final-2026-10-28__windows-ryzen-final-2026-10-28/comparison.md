# Cross-machine comparison

Each run was analyzed on its own machine; this file only places their tables side by side. The machines differ in processor, operating system, and Python build, so a difference between them cannot be attributed to the operating system alone. Compare rankings, ratios, and budget verdicts rather than absolute times.

## Machines

| Run | Processor | Logical CPUs | RAM | Platform | Python | Harness |
| --- | --- | --- | --- | --- | --- | --- |
| macos-m4pro-final-2026-10-28 | Apple M4 Pro | 12 | 24 GiB | macOS-15.2-arm64-arm-64bit-Mach-O | 3.13.5 | corrected |
| windows-ryzen-final-2026-10-28 | AMD Ryzen 7 PRO 6850U with Radeon Graphics | 16 | 28 GiB | Windows-11-10.0.26200-SP0 | 3.12.10 | corrected |

All runs used the same registered configuration (SHA-256 fed42fd6b7c6f09c0870817614bc1d841c6766f99437cbfda8932e9047045aa4).
All runs include the supplementary experiments with the same config/supplementary.yaml.

## Research question 1: baseline verification time

| Algorithm | macos-m4pro-final-2026-10-28 median / p95 ms | windows-ryzen-final-2026-10-28 median / p95 ms | windows-ryzen-final-2026-10-28 / macos-m4pro-final-2026-10-28 |
| --- | --- | --- | --- |
| Argon2id | 13.53 / 15.71 | 21.43 / 23.86 | 1.58x |
| bcrypt | 41.78 / 43.66 | 46.35 / 47.09 | 1.11x |
| PBKDF2-HMAC-SHA256 | 48.27 / 49.23 | 207.64 / 211.74 | 4.30x |

- macos-m4pro-final-2026-10-28: Argon2id < bcrypt < PBKDF2-HMAC-SHA256
- windows-ryzen-final-2026-10-28: Argon2id < bcrypt < PBKDF2-HMAC-SHA256
- Ranking by median verification time is the same on every machine.

Ratio of median verification times within each machine. A ratio that holds across machines does not depend on the hardware's absolute speed.

| Pair | macos-m4pro-final-2026-10-28 | windows-ryzen-final-2026-10-28 |
| --- | --- | --- |
| bcrypt / Argon2id | 3.09x | 2.16x |
| PBKDF2-HMAC-SHA256 / Argon2id | 3.57x | 9.69x |
| PBKDF2-HMAC-SHA256 / bcrypt | 1.16x | 4.48x |

## Research question 2: parameter sweeps

| Algorithm | Parameter | macos-m4pro-final-2026-10-28 median ms | windows-ryzen-final-2026-10-28 median ms | windows-ryzen-final-2026-10-28 / macos-m4pro-final-2026-10-28 |
| --- | --- | --- | --- | --- |
| Argon2id | 19 MiB | 13.53 | 21.43 | 1.58x |
| Argon2id | 32 MiB | 25.52 | 39.88 | 1.56x |
| Argon2id | 46 MiB | 39.53 | 59.02 | 1.49x |
| Argon2id | 64 MiB | 57.82 | 83.77 | 1.45x |
| Argon2id | 128 MiB | 121.05 | 179.59 | 1.48x |
| bcrypt | 10 | 41.78 | 46.35 | 1.11x |
| bcrypt | 11 | 82.75 | 92.54 | 1.12x |
| bcrypt | 12 | 164.93 | 184.48 | 1.12x |
| bcrypt | 13 | 329.48 | 368.30 | 1.12x |
| bcrypt | 14 | 659.27 | 737.26 | 1.12x |
| PBKDF2-HMAC-SHA256 | 600000 | 48.27 | 207.64 | 4.30x |
| PBKDF2-HMAC-SHA256 | 900000 | 72.31 | 311.60 | 4.31x |
| PBKDF2-HMAC-SHA256 | 1200000 | 96.41 | 415.22 | 4.31x |
| PBKDF2-HMAC-SHA256 | 1500000 | 120.35 | 518.15 | 4.31x |

- Argon2id, 19 MiB to 128 MiB: 8.95x on macos-m4pro-final-2026-10-28, 8.38x on windows-ryzen-final-2026-10-28.
- bcrypt, 10 to 14: 15.78x on macos-m4pro-final-2026-10-28, 15.90x on windows-ryzen-final-2026-10-28.
- PBKDF2-HMAC-SHA256, 600000 to 1500000: 2.49x on macos-m4pro-final-2026-10-28, 2.50x on windows-ryzen-final-2026-10-28.

## Research question 3: budgets at the reference load

Thread pool with 4 workers. Budget A is p95 at most 500 ms and budget B at most 1000 ms, each with at least 10 verifications per second.

| Algorithm | Parameter | macos-m4pro-final-2026-10-28 p95, A/B | windows-ryzen-final-2026-10-28 p95, A/B | Same verdict |
| --- | --- | --- | --- | --- |
| Argon2id | 19 MiB | 21.6 ms, pass/pass | 45.4 ms, pass/pass | yes |
| Argon2id | 32 MiB | 35.8 ms, pass/pass | 74.8 ms, pass/pass | yes |
| Argon2id | 46 MiB | 52.1 ms, pass/pass | 104.7 ms, pass/pass | yes |
| Argon2id | 64 MiB | 71.6 ms, pass/pass | 149.3 ms, pass/pass | yes |
| Argon2id | 128 MiB | 143.6 ms, pass/pass | 284.9 ms, pass/pass | yes |
| bcrypt | 10 | 51.3 ms, pass/pass | 62.7 ms, pass/pass | yes |
| bcrypt | 11 | 96.1 ms, pass/pass | 111.0 ms, pass/pass | yes |
| bcrypt | 12 | 187.9 ms, pass/pass | 214.4 ms, pass/pass | yes |
| bcrypt | 13 | 370.4 ms, pass/pass | 445.7 ms, fail/fail | no |
| bcrypt | 14 | 737.2 ms, fail/fail | 821.3 ms, fail/fail | yes |
| PBKDF2-HMAC-SHA256 | 600000 | 58.6 ms, pass/pass | 274.3 ms, pass/pass | yes |
| PBKDF2-HMAC-SHA256 | 900000 | 85.9 ms, pass/pass | 389.4 ms, pass/pass | yes |
| PBKDF2-HMAC-SHA256 | 1200000 | 120.4 ms, pass/pass | 519.8 ms, fail/fail | no |
| PBKDF2-HMAC-SHA256 | 1500000 | 137.0 ms, pass/pass | 634.5 ms, fail/fail | no |

- macos-m4pro-final-2026-10-28: 13 of 14 meet budget A and 13 meet budget B.
- windows-ryzen-final-2026-10-28: 10 of 14 meet budget A and 10 meet budget B.
- The budget verdicts agree for 11 of 14 configurations.

Highest registered thread-pool throughput and the worker count where it occurred. The worker count depends on each machine's core count.

| Algorithm | Parameter | macos-m4pro-final-2026-10-28 | windows-ryzen-final-2026-10-28 |
| --- | --- | --- | --- |
| Argon2id | 19 MiB | 396/s at 8 | 152/s at 8 |
| Argon2id | 32 MiB | 216/s at 8 | 91/s at 8 |
| Argon2id | 46 MiB | 150/s at 8 | 62/s at 8 |
| Argon2id | 64 MiB | 108/s at 8 | 45/s at 8 |
| Argon2id | 128 MiB | 52/s at 8 | 22/s at 8 |
| bcrypt | 10 | 163/s at 8 | 135/s at 8 |
| bcrypt | 11 | 82/s at 8 | 70/s at 8 |
| bcrypt | 12 | 42/s at 8 | 35/s at 8 |
| bcrypt | 13 | 21/s at 8 | 18/s at 8 |
| bcrypt | 14 | 11/s at 8 | 9/s at 8 |
| PBKDF2-HMAC-SHA256 | 600000 | 144/s at 8 | 24/s at 8 |
| PBKDF2-HMAC-SHA256 | 900000 | 99/s at 8 | 16/s at 8 |
| PBKDF2-HMAC-SHA256 | 1200000 | 76/s at 8 | 12/s at 8 |
| PBKDF2-HMAC-SHA256 | 1500000 | 59/s at 8 | 10/s at 8 |

## Supplementary: equal verification time

The parameter each machine reached for the same target time, with its measured median. A faster machine buys more work in the same time.

| Target ms | Algorithm | macos-m4pro-final-2026-10-28 | windows-ryzen-final-2026-10-28 |
| --- | --- | --- | --- |
| 100 | Argon2id | 102 MiB (97.1 ms) | 72 MiB (94.6 ms) |
| 100 | bcrypt | 11 (85.1 ms) | 11 (93.1 ms) |
| 100 | PBKDF2-HMAC-SHA256 | 1260000 (101.3 ms) | 270000 (97.8 ms) |
| 100 | scrypt | 65536 (97.5 ms) | 32768 (121.1 ms) |
| 250 | Argon2id | 249 MiB (247.3 ms) | 183 MiB (253.5 ms) |
| 250 | bcrypt | 13 (327.2 ms) | 12 (185.0 ms) |
| 250 | PBKDF2-HMAC-SHA256 | 3200000 (253.5 ms) | 680000 (240.4 ms) |
| 250 | scrypt | 131072 (196.8 ms) | 65536 (244.8 ms) |
