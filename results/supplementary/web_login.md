# Optional: end-to-end login load test

Declared in config/web_login.yaml on 2026-10-29, after both final runs (SHA-256 610953cb0f22e80aa45bc95a3b962d7976352c4711a5ca95af843a43ce4c2d4a). It is not part of the registered or supplementary designs and does not change their answers.

A FastAPI service with one process (1 worker) verifies POST /login requests against hashes of the synthetic corpus at each baseline. Locust clients on the same machine send requests with no wait with a configured duration of 30 s per row; each request has a 10% probability of using a wrong password of the same length, which must return 401. A failure means the response differs from the expected status (200 for correct passwords, 401 for wrong passwords).

Requests/s includes both accepted logins and correctly rejected wrong-password attempts. The CSV reports correct-login throughput separately. Correct n is the sample count used for the correct-password latency percentiles.

| Algorithm | Clients | Requests/s | Correct n | Correct median ms | Correct p95 ms | Failures | Budget A thresholds at 4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Argon2id | 1 | 72.2 | 1824 | 14 | 15 | 0 of 2025 |  |
| Argon2id | 4 | 229.0 | 5945 | 17 | 19 | 0 of 6646 | yes |
| Argon2id | 16 | 416.8 | 10877 | 37 | 56 | 0 of 12095 |  |
| bcrypt | 1 | 21.9 | 576 | 45 | 47 | 0 of 638 |  |
| bcrypt | 4 | 85.1 | 2222 | 47 | 48 | 0 of 2474 | yes |
| bcrypt | 16 | 205.0 | 5358 | 76 | 100 | 0 of 5954 |  |
| PBKDF2-HMAC-SHA256 | 1 | 20.2 | 535 | 49 | 50 | 0 of 588 |  |
| PBKDF2-HMAC-SHA256 | 4 | 76.8 | 1998 | 50 | 61 | 0 of 2232 | yes |
| PBKDF2-HMAC-SHA256 | 16 | 134.4 | 3531 | 120 | 170 | 0 of 3905 |  |
| scrypt | 1 | 4.6 | 58 | 210 | 230 | 0 of 67 |  |
| scrypt | 4 | 14.9 | 381 | 250 | 320 | 0 of 432 | yes |
| scrypt | 16 | 28.8 | 758 | 550 | 620 | 0 of 834 |  |

The last column applies budget A's thresholds (p95 at most 500 ms, at least 10 per second) to the 4-client row for orientation only. Research question 3 is answered by the registered concurrency experiment.

Compared with the registered concurrency experiment, each request here also pays for HTTP, JSON parsing, and FastAPI's thread pool, and the locust clients use CPU on the same machine. Locust rounds response times above 100 ms to two significant digits, so the percentiles are coarser than in the other tables.

The benchmark uses synthetic passwords only. It does not perform password guessing against the service.

## Measurement qualifications

- scrypt-n131072-r8-p1 at 1 clients has only 58 correct requests; p95 and p99 are based on very few tail observations and should be treated as exploratory.
- scrypt-n131072-r8-p1 at 1 clients: request count divided by reported Requests/s implies a statistics interval of approximately 14.5 s, shorter than the configured 30 s. This is inferred from aggregate statistics, not a recorded wall-clock duration. Investigate startup/final-statistics collection and repeat this case before treating it as a full-duration result.
