"""Checks for the supplementary harness and the added statistics. These are not experimental results."""

import statistics
import unittest
from concurrent.futures import ThreadPoolExecutor

from password_benchmark.analyze_supplementary import saturation_point
from password_benchmark.cases import configured_memory_bytes, make_config_id
from password_benchmark.concurrent import _start_workers, _thread_ready
from password_benchmark.config import load_config
from password_benchmark.equal_latency import calibrate
from password_benchmark.hashers import make_hasher
from password_benchmark.input_handling import evaluate_input_handling
from password_benchmark.memory import probe_concurrent_rss
from password_benchmark.stats import (
    bootstrap_median_contrast_ci,
    bootstrap_percentile_ci,
    cliffs_delta_from_u,
    holm_adjust,
    mann_whitney,
)
from password_benchmark.supplementary import load_supplementary, smoke_supplementary
from password_benchmark.wrong_password import interleaved_schedule, wrong_variant

FAST = {
    "argon2id": {"memory_kib": 8192, "time_cost": 1, "parallelism": 1, "hash_len": 32, "salt_len": 16},
    "bcrypt": {"cost": 4},
    "pbkdf2_sha256": {"iterations": 1000, "hash_len": 32, "salt_len": 16},
    "scrypt": {"n": 1024, "r": 8, "p": 1, "hash_len": 32, "salt_len": 16},
}


class SupplementaryDesignTests(unittest.TestCase):
    def test_supplementary_file_extends_without_changing_the_registered_design(self):
        main = load_config()
        supp = load_supplementary(main)
        self.assertEqual(tuple(main.algorithms), ("argon2id", "bcrypt", "pbkdf2_sha256"))
        self.assertEqual(tuple(supp.extension.algorithms), ("argon2id", "scrypt"))
        self.assertEqual(supp.extension.algorithms["argon2id"]["baseline"], main.algorithms["argon2id"]["baseline"])
        # OWASP minimum for scrypt: N=2^17, r=8, p=1.
        self.assertEqual(supp.baselines()["scrypt"]["n"], 2**17)
        self.assertEqual(configured_memory_bytes(supp.baselines()["scrypt"]), 128 * 1024 * 1024)
        self.assertEqual(supp.extra_workers, [16, 32])
        self.assertEqual(supp.tight_budgets_ms, [100, 250])
        self.assertTrue(set(supp.extra_workers).isdisjoint(main.concurrency_workers))
        self.assertNotEqual(supp.sha256, main.config_sha256)

    def test_smoke_supplementary_is_small(self):
        smoke = smoke_supplementary(load_supplementary())
        self.assertEqual(smoke.main.password_count, 2)
        self.assertLess(smoke.baselines()["scrypt"]["n"], 2**17)
        self.assertEqual(load_supplementary().baselines()["scrypt"]["n"], 2**17)

    def test_scrypt_config_id(self):
        self.assertEqual(make_config_id("scrypt", FAST["scrypt"]), "scrypt-n1024-r8-p1")
        with self.assertRaises(ValueError):
            make_hasher("scrypt", dict(FAST["scrypt"], n=1000))


class StatisticsTests(unittest.TestCase):
    def test_bootstrap_interval_contains_the_estimate(self):
        values = [10.0 + (index % 7) * 0.1 for index in range(300)]
        low, high = bootstrap_percentile_ci(values, 50, 2000, 0.95, 1)
        self.assertLessEqual(low, statistics.median(values))
        self.assertGreaterEqual(high, statistics.median(values))
        again = bootstrap_percentile_ci(values, 50, 2000, 0.95, 1)
        self.assertEqual((low, high), again)

    def test_median_contrast(self):
        first = [20.0 + (index % 5) * 0.1 for index in range(200)]
        second = [10.0 + (index % 5) * 0.1 for index in range(200)]
        low, high = bootstrap_median_contrast_ci(first, second, 1000, 0.95, 2, ratio=True)
        self.assertTrue(1.9 < low <= high < 2.1)
        low, high = bootstrap_median_contrast_ci(first, second, 1000, 0.95, 2, ratio=False)
        self.assertTrue(9.9 <= low <= high <= 10.1)

    def test_holm_adjustment(self):
        self.assertEqual(holm_adjust([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
        self.assertEqual(holm_adjust([0.5, 0.9]), [1.0, 1.0])

    def test_cliffs_delta(self):
        self.assertEqual(cliffs_delta_from_u(100, 10, 10), 1.0)
        self.assertEqual(cliffs_delta_from_u(0, 10, 10), -1.0)
        result = mann_whitney([5, 6, 7], [1, 2, 3])
        self.assertEqual(result["cliffs_delta"], 1.0)


class ConcurrencyHarnessTests(unittest.TestCase):
    def test_workers_start_before_the_timed_batch(self):
        with ThreadPoolExecutor(max_workers=3) as executor:
            _start_workers(executor, 3, _thread_ready)
            self.assertEqual(len(executor._threads), 3)

    def test_saturation_point(self):
        def row(workers, throughput, p95):
            return {"workers": workers, "throughput_per_second": throughput, "p95_ms": p95, "skipped": False}

        scaling = [row(1, 10, 100), row(2, 20, 100), row(4, 40, 110), row(8, 42, 190)]
        self.assertEqual(saturation_point(scaling, 0.10, 2.0)[0], 8)
        slow = [row(1, 10, 100), row(2, 20, 250)]
        self.assertIn("p95", saturation_point(slow, 0.10, 2.0)[1])
        self.assertIsNone(saturation_point([row(1, 10, 100), row(2, 20, 100)], 0.10, 2.0))

    def test_concurrent_memory_probe_counts_every_verification(self):
        params = FAST["argon2id"]
        hasher = make_hasher("argon2id", params)
        tasks = [{"password": f"synthetic-{index}", "encoded": hasher.hash_password(f"synthetic-{index}")} for index in range(2)]
        probed = probe_concurrent_rss("argon2id", params, tasks, timeout=60)
        self.assertTrue(probed["ok"])
        # Two 8 MiB verifications at once; allow for allocator and timing slack.
        self.assertGreater(probed["delta_rss"], 12 * 1024 * 1024)


class EqualLatencyTests(unittest.TestCase):
    def test_linear_calibration_converges(self):
        spec = {"kind": "linear", "start": 1000, "step": 10}
        chosen, trail = calibrate(spec, 100.0, lambda value: value * 0.04, rounds=6, tolerance=0.05)
        self.assertEqual(chosen, 2500)
        self.assertLessEqual(len(trail), 3)

    def test_doubling_calibration_picks_the_nearest_step(self):
        spec = {"kind": "doubling", "values": [8, 9, 10, 11, 12, 13], "start": 10}
        chosen, trail = calibrate(spec, 100.0, lambda cost: 40.0 * 2 ** (cost - 10), rounds=6, tolerance=0.05)
        # 80 ms (cost 11) is closer to 100 ms in ratio than 160 ms (cost 12).
        self.assertEqual(chosen, 11)
        self.assertEqual({item["value"] for item in trail}, {10, 11, 12})


class WrongPasswordAndInputTests(unittest.TestCase):
    def test_wrong_variant_keeps_length(self):
        charset = "abc"
        self.assertEqual(wrong_variant("aac", charset), "aaa")
        self.assertEqual(len(wrong_variant("abcabc", charset)), 6)

    def test_schedule_is_balanced_and_seeded(self):
        schedule = interleaved_schedule(3, 4, 7)
        self.assertEqual(sum(kind == "correct" for _, kind in schedule), 12)
        self.assertEqual(sum(kind == "wrong" for _, kind in schedule), 12)
        self.assertEqual(schedule, interleaved_schedule(3, 4, 7))

    def test_hmac_prehash_and_zero_padding_pairs(self):
        records = evaluate_input_handling(FAST, [64, 65], 20)
        found = {(record["algorithm"], record["name"]): record for record in records}
        for algorithm in ("pbkdf2_sha256", "scrypt"):
            self.assertIs(found[(algorithm, "sha256_of_65_bytes")]["same_result"], True)
            self.assertIs(found[(algorithm, "trailing_nul")]["same_result"], True)
            self.assertIs(found[(algorithm, "sha256_of_64_bytes")]["same_result"], False)
        for name in ("sha256_of_65_bytes", "trailing_nul"):
            self.assertIs(found[("argon2id", name)]["same_result"], False)
            self.assertIs(found[("bcrypt", name)]["same_result"], False)


if __name__ == "__main__":
    unittest.main()
