# Results summary

## Machine

- Python: 3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
- OpenSSL: OpenSSL 3.0.16 11 Feb 2025
- CPU: AMD Ryzen 7 PRO 6850U with Radeon Graphics (8 physical cores, 16 logical)
- RAM: 27.8 GiB
- Platform: Windows-11-10.0.26200-SP0
- Power scheme: Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e (Balanced)
- Libraries: argon2-cffi 25.1.0, bcrypt 5.0.0, psutil 7.2.2, pandas 3.1.0, matplotlib 3.11.2, PyYAML 6.0.3
- Config SHA-256: d2ef193fcf236a5af27e744573638fd96394418979028c4f7954f486104de55c
- The full package list is in environment.json.

## Registered rules

Warmup verifications discarded per configuration: 10. Pilot verifications: 5. Measured repeats per password: 25, or 10 when the pilot median exceeds 2000 ms.
Budget A requires p95 latency at or below 500 ms and throughput of at least 10 verifications per second at 4 concurrent workers. Budget B uses the same throughput rule and a p95 limit of 1000 ms. Both conditions are required.
Verification time excludes salt generation and hash construction. Those happen before the timed calls.
Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.

## Research question 1

Under the baseline configurations, median verification latency was Argon2id 21.72 ms (p95 23.36 ms, CPU 15.62 ms); bcrypt 105.86 ms (p95 106.38 ms, CPU 109.38 ms); PBKDF2-HMAC-SHA256 216.62 ms (p95 599.45 ms, CPU 218.75 ms).

| Algorithm | Median ms | p95 ms | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 21.72 | 23.36 | 15.62 | 18.2 | 19.0 | 1000 |
| bcrypt | 105.86 | 106.38 | 109.38 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 216.62 | 599.45 | 218.75 | 0.0 |  | 1000 |

## Research question 2

For Argon2id, raising memory_kib from 19 MiB to 128 MiB changed median verification latency from 21.72 ms to 369.18 ms.
For bcrypt, raising cost from 10 to 14 changed median verification latency from 105.86 ms to 1664.26 ms.
For PBKDF2-HMAC-SHA256, raising iterations from 600000 to 1500000 changed median verification latency from 216.62 ms to 536.34 ms.

## Research question 3

At 4 concurrent thread-pool verifications, configurations inside budget A: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000.
Inside budget B but outside budget A: none.
Outside both budgets: bcrypt-c13, bcrypt-c14, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000.

| Configuration | p95 ms | Per second | Peak RSS MiB | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 52.58 | 98.1 | 100.1 | yes | yes |
| argon2id-m32768-t2-p1 | 79.31 | 60.1 | 154.1 | yes | yes |
| argon2id-m47104-t2-p1 | 101.29 | 41.8 | 209.8 | yes | yes |
| argon2id-m65536-t2-p1 | 156.41 | 29.5 | 281.8 | yes | yes |
| argon2id-m131072-t2-p1 | 286.20 | 14.6 | 537.7 | yes | yes |
| bcrypt-c10 | 65.93 | 68.7 | 31.6 | yes | yes |
| bcrypt-c11 | 126.76 | 35.4 | 31.6 | yes | yes |
| bcrypt-c12 | 242.00 | 18.1 | 31.7 | yes | yes |
| bcrypt-c13 | 465.65 | 9.4 | 31.7 | no | no |
| bcrypt-c14 | 931.56 | 4.8 | 31.6 | no | no |
| pbkdf2-sha256-i600000 | 267.33 | 15.9 | 31.6 | yes | yes |
| pbkdf2-sha256-i900000 | 411.68 | 10.4 | 31.6 | yes | yes |
| pbkdf2-sha256-i1200000 | 509.11 | 8.1 | 31.6 | no | no |
| pbkdf2-sha256-i1500000 | 651.27 | 6.4 | 31.6 | no | no |

### Process-pool check

argon2id-m19456-t2-p1: thread pool 98.1/s, process pool 60.0/s, relative difference 38.9%, outside the registered 15% agreement range.
bcrypt-c10: thread pool 68.7/s, process pool 53.0/s, relative difference 22.8%, outside the registered 15% agreement range.
pbkdf2-sha256-i600000: thread pool 15.9/s, process pool 13.8/s, relative difference 13.0%, within the registered 15% agreement range.

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
| argon2id-m19456-t2-p1 | 22.93 | 40 |
| argon2id-m32768-t2-p1 | 40.61 | 40 |
| argon2id-m47104-t2-p1 | 58.36 | 40 |
| argon2id-m65536-t2-p1 | 82.41 | 40 |
| argon2id-m131072-t2-p1 | 369.70 | 40 |
| bcrypt-c10 | 105.77 | 40 |
| bcrypt-c11 | 211.39 | 40 |
| bcrypt-c12 | 423.00 | 40 |
| bcrypt-c13 | 843.78 | 40 |
| bcrypt-c14 | 1665.71 | 40 |
| pbkdf2-sha256-i600000 | 645.17 | 40 |
| pbkdf2-sha256-i900000 | 325.80 | 40 |
| pbkdf2-sha256-i1200000 | 439.17 | 40 |
| pbkdf2-sha256-i1500000 | 560.07 | 40 |

## Scope

These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.
The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.
