# Results summary

## Machine

- Python: 3.13.5 (main, Jun 11 2025, 15:36:57) [Clang 16.0.0 (clang-1600.0.26.6)]
- OpenSSL: OpenSSL 3.5.1 1 Jul 2025
- CPU: arm (12 physical cores, 12 logical)
- RAM: 24.0 GiB
- Platform: macOS-15.2-arm64-arm-64bit-Mach-O
- Power scheme: unavailable: [Errno 2] No such file or directory: 'powercfg'
- Libraries: argon2-cffi 25.1.0, bcrypt 5.0.0, psutil 7.2.2, pandas 3.1.0, matplotlib 3.11.2, PyYAML 6.0.3
- Config SHA-256: fed42fd6b7c6f09c0870817614bc1d841c6766f99437cbfda8932e9047045aa4
- The full package list is in environment.json.

## Registered rules

Warmup verifications discarded per configuration: 10. Pilot verifications: 5. Measured repeats per password: 25, or 10 when the pilot median exceeds 2000 ms.
Budget A requires p95 latency at or below 500 ms and throughput of at least 10 verifications per second at 4 concurrent workers. Budget B uses the same throughput rule and a p95 limit of 1000 ms. Both conditions are required.
Verification time excludes salt generation and hash construction. Those happen before the timed calls.
Memory is the growth in the process peak working set during verification, measured in a fresh process. A value of only a few MiB is measurement noise. Argon2id's configured memory is the setting that matters.

## Research question 1

Under the baseline configurations, median verification latency was Argon2id 12.87 ms (p95 14.29 ms, CPU 12.87 ms); bcrypt 41.09 ms (p95 42.48 ms, CPU 41.06 ms); PBKDF2-HMAC-SHA256 45.76 ms (p95 46.72 ms, CPU 45.74 ms).

| Algorithm | Median ms | p95 ms | CPU ms | RSS delta MiB | Configured MiB | n |
| --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 12.87 | 14.29 | 12.87 | 19.0 | 19.0 | 1000 |
| bcrypt | 41.09 | 42.48 | 41.06 | 0.0 |  | 1000 |
| PBKDF2-HMAC-SHA256 | 45.76 | 46.72 | 45.74 | 0.0 |  | 1000 |

## Research question 2

For Argon2id, raising memory_kib from 19 MiB to 128 MiB changed median verification latency from 12.87 ms to 115.11 ms.
For bcrypt, raising cost from 10 to 14 changed median verification latency from 41.09 ms to 657.64 ms.
For PBKDF2-HMAC-SHA256, raising iterations from 600000 to 1500000 changed median verification latency from 45.76 ms to 116.37 ms.

## Research question 3

At 4 concurrent thread-pool verifications, configurations inside budget A: argon2id-m19456-t2-p1, argon2id-m32768-t2-p1, argon2id-m47104-t2-p1, argon2id-m65536-t2-p1, argon2id-m131072-t2-p1, bcrypt-c10, bcrypt-c11, bcrypt-c12, bcrypt-c13, pbkdf2-sha256-i600000, pbkdf2-sha256-i900000, pbkdf2-sha256-i1200000, pbkdf2-sha256-i1500000.
Inside budget B but outside budget A: none.
Outside both budgets: bcrypt-c14.

| Configuration | p95 ms | Per second | Peak RSS MiB | Budget A | Budget B |
| --- | --- | --- | --- | --- | --- |
| argon2id-m19456-t2-p1 | 22.45 | 219.9 | 116.8 | yes | yes |
| argon2id-m32768-t2-p1 | 36.80 | 121.4 | 310.4 | yes | yes |
| argon2id-m47104-t2-p1 | 52.78 | 82.4 | 590.7 | yes | yes |
| argon2id-m65536-t2-p1 | 72.43 | 59.7 | 865.9 | yes | yes |
| argon2id-m131072-t2-p1 | 144.27 | 28.4 | 1236.9 | yes | yes |
| bcrypt-c10 | 51.95 | 82.5 | 1463.2 | yes | yes |
| bcrypt-c11 | 97.05 | 43.0 | 1302.3 | yes | yes |
| bcrypt-c12 | 186.24 | 21.9 | 1189.3 | yes | yes |
| bcrypt-c13 | 370.67 | 11.0 | 922.2 | yes | yes |
| bcrypt-c14 | 737.67 | 5.5 | 719.3 | no | no |
| pbkdf2-sha256-i600000 | 52.74 | 76.9 | 719.3 | yes | yes |
| pbkdf2-sha256-i900000 | 82.87 | 51.0 | 719.3 | yes | yes |
| pbkdf2-sha256-i1200000 | 113.52 | 39.2 | 719.4 | yes | yes |
| pbkdf2-sha256-i1500000 | 142.75 | 31.0 | 719.4 | yes | yes |

### Process-pool check

argon2id-m19456-t2-p1: thread pool 219.9/s, process pool 183.2/s, relative difference 16.7%, outside the registered 15% agreement range.
bcrypt-c10: thread pool 82.5/s, process pool 73.2/s, relative difference 11.3%, within the registered 15% agreement range.
pbkdf2-sha256-i600000: thread pool 76.9/s, process pool 69.0/s, relative difference 10.3%, within the registered 15% agreement range.

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
| argon2id-m19456-t2-p1 | 12.89 | 40 |
| argon2id-m32768-t2-p1 | 27.21 | 40 |
| argon2id-m47104-t2-p1 | 37.53 | 40 |
| argon2id-m65536-t2-p1 | 54.01 | 40 |
| argon2id-m131072-t2-p1 | 115.32 | 40 |
| bcrypt-c10 | 41.05 | 40 |
| bcrypt-c11 | 82.02 | 40 |
| bcrypt-c12 | 164.18 | 40 |
| bcrypt-c13 | 328.02 | 40 |
| bcrypt-c14 | 657.44 | 40 |
| pbkdf2-sha256-i600000 | 45.60 | 40 |
| pbkdf2-sha256-i900000 | 68.83 | 40 |
| pbkdf2-sha256-i1200000 | 92.65 | 40 |
| pbkdf2-sha256-i1500000 | 116.17 | 40 |

## Scope

These findings apply to this machine, these library versions, and these configurations. They are not a universal ranking of the algorithms.
The benchmark uses synthetic passwords only. It does not perform password cracking and it does not use real credentials.
