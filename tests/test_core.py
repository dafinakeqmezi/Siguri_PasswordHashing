"""Checks for the benchmark harness. These are not the experimental results."""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from password_benchmark.bcrypt_length import evaluate_bcrypt_lengths, length_cases
from password_benchmark.cases import build_cases
from password_benchmark.config import load_config, smoke_config
from password_benchmark.hashers import make_hasher
from password_benchmark.memory import probe_verify_rss, should_skip_for_memory
from password_benchmark.passwords import generate_passwords
from password_benchmark.paths import CONFIG_PATH
from password_benchmark.stats import median, meets_budget, percentile
from password_benchmark.environment import _cpu_name, _power_scheme, _cpu_frequency
from password_benchmark.mem_worker import _peak_bytes
from password_benchmark.archive import save_run


class ArchiveTests(unittest.TestCase):
    def test_saved_run_keeps_data_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder in ("data/raw", "results/smoke", "config", "password_benchmark", "tests"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            for filename in ("data/raw/latency.jsonl", "results/environment.json", "results/summary.md", "README.md", "requirements.txt", "requirements-lock.txt"):
                (root / filename).write_text("original", encoding="utf-8")
            (root / "results/smoke/summary.md").write_text("smoke", encoding="utf-8")
            saved = save_run("mac-test", root)
            (root / "results/summary.md").write_text("next run", encoding="utf-8")
            self.assertEqual((saved / "results/summary.md").read_text(), "original")
            self.assertFalse((saved / "results/smoke").exists())
            self.assertTrue((saved / "manifest.json").is_file())
            with self.assertRaises(FileExistsError):
                save_run("mac-test", root)
            with self.assertRaises(ValueError):
                save_run("../outside", root)
            (root / "results/RUN_IN_PROGRESS").touch()
            with self.assertRaises(RuntimeError):
                save_run("busy", root)


class PlatformTests(unittest.TestCase):
    def test_platform_specific_environment_commands(self):
        for system, cpu_command, power_command in (
            ("Windows", "powershell", "powercfg"),
            ("Darwin", "sysctl", "pmset"),
        ):
            with self.subTest(system=system), patch(
                "password_benchmark.environment.platform.system", return_value=system
            ), patch("password_benchmark.environment.subprocess.check_output", return_value="Example output\n") as command:
                self.assertEqual(_cpu_name(), "Example output")
                self.assertEqual(command.call_args.args[0][0], cpu_command)
                self.assertEqual(_power_scheme(), "Example output")
                self.assertEqual(command.call_args.args[0][0], power_command)

    def test_apple_silicon_frequency_is_not_reported(self):
        with patch("password_benchmark.environment.platform.system", return_value="Darwin"), patch(
            "password_benchmark.environment.platform.machine", return_value="arm64"
        ), patch("password_benchmark.environment.psutil.cpu_freq", create=True) as frequency:
            self.assertIsNone(_cpu_frequency())
            frequency.assert_not_called()

    def test_peak_memory_backends_and_units(self):
        with patch("password_benchmark.mem_worker.platform.system", return_value="Windows"), patch(
            "password_benchmark.mem_worker.psutil.Process"
        ) as process:
            process.return_value.memory_info.return_value.peak_wset = 123456
            self.assertEqual(_peak_bytes(), 123456)
        # A fake resource module also exercises the Unix branch on Windows CI.
        resource = Mock()
        resource.getrusage.return_value.ru_maxrss = 123456
        with patch.dict("sys.modules", {"resource": resource}):
            for system, expected in (("Darwin", 123456), ("Linux", 123456 * 1024)):
                with self.subTest(system=system), patch(
                    "password_benchmark.mem_worker.platform.system", return_value=system
                ):
                    self.assertEqual(_peak_bytes(), expected)


class StatsTests(unittest.TestCase):
    def test_median_and_pandas_quantile_match(self):
        values = [10, 20, 30, 40, 100]
        self.assertEqual(median(values), 30)
        self.assertAlmostEqual(percentile(values, 95), float(pd.Series(values).quantile(0.95)))

    def test_budget_requires_latency_and_throughput(self):
        self.assertTrue(meets_budget(400, 12, 500, 10))
        self.assertFalse(meets_budget(400, 9, 500, 10))
        self.assertFalse(meets_budget(700, 12, 500, 10))


class DesignTests(unittest.TestCase):
    def test_registered_baselines_and_grid(self):
        cfg = load_config()
        self.assertEqual(cfg.seed, 20261023)
        self.assertEqual(cfg.password_count, 40)
        self.assertEqual(cfg.password_lengths, [12, 16, 24, 32])
        self.assertEqual(cfg.budget_a_ms, 500)
        self.assertEqual(cfg.budget_b_ms, 1000)
        self.assertEqual(cfg.throughput_min, 10)
        self.assertEqual(cfg.reference_workers, 4)
        self.assertEqual(cfg.algorithms["argon2id"]["baseline"]["memory_kib"], 19456)
        self.assertEqual(cfg.algorithms["argon2id"]["baseline"]["time_cost"], 2)
        self.assertEqual(cfg.algorithms["argon2id"]["baseline"]["parallelism"], 1)
        self.assertEqual(cfg.algorithms["bcrypt"]["baseline"]["cost"], 10)
        self.assertEqual(cfg.algorithms["pbkdf2_sha256"]["baseline"]["iterations"], 600000)
        cases = build_cases(cfg)
        self.assertEqual(len(cases), 14)
        self.assertEqual(sum("baseline" in case.roles for case in cases), 3)

    def test_smoke_config_does_not_rewrite_the_registered_file(self):
        before = CONFIG_PATH.read_bytes()
        cfg = load_config()
        smoke = smoke_config(cfg)
        self.assertEqual(CONFIG_PATH.read_bytes(), before)
        self.assertEqual(cfg.algorithms["pbkdf2_sha256"]["baseline"]["iterations"], 600000)
        self.assertEqual(smoke.algorithms["pbkdf2_sha256"]["baseline"]["iterations"], 2000)
        self.assertEqual(smoke.reference_workers, 2)

    def test_corpus_is_synthetic_ascii_and_reproducible(self):
        cfg = load_config()
        first = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
        second = generate_passwords(cfg.password_count, cfg.password_lengths, cfg.charset, cfg.seed)
        self.assertEqual([item.password for item in first], [item.password for item in second])
        self.assertEqual([item.byte_length for item in first[:4]], [12, 16, 24, 32])
        self.assertTrue(all(item.byte_length == item.char_length <= 72 for item in first))
        self.assertTrue(all(set(item.password) <= set(cfg.charset) for item in first))


class HasherTests(unittest.TestCase):
    def test_fast_parameters_roundtrip_and_reject_the_wrong_password(self):
        cases = [
            ("argon2id", {"memory_kib": 8192, "time_cost": 1, "parallelism": 1, "hash_len": 32, "salt_len": 16}),
            ("bcrypt", {"cost": 4}),
            ("pbkdf2_sha256", {"iterations": 1000, "hash_len": 32, "salt_len": 16}),
        ]
        for algorithm, params in cases:
            hasher = make_hasher(algorithm, params)
            encoded = hasher.hash_password("synthetic-password")
            self.assertTrue(hasher.verify("synthetic-password", encoded))
            self.assertFalse(hasher.verify("different-password", encoded))

    def test_bcrypt_length_harness_records_each_case(self):
        cases = length_cases([71, 72, 73, 100])
        utf8 = next(case for case in cases if case["name"] == "utf8_boundary")
        self.assertEqual(len(utf8["password"]), 73)
        self.assertEqual(utf8["password"][:72], utf8["alternate"][:72])
        self.assertNotEqual(utf8["password"], utf8["alternate"])
        records = evaluate_bcrypt_lengths(4, [71, 72, 73, 100])
        self.assertTrue(all(record["self_verify"] is True for record in records if record["password_bytes"] <= 72))
        self.assertTrue(all(record["error"] and "72" in record["error"] for record in records if record["password_bytes"] > 72))
        nul = next(record for record in records if record["name"] == "nul_inside_first_72")
        self.assertLessEqual(nul["password_bytes"], 72)
        self.assertIs(nul["truncated_at_nul_verify"], False)
        self.assertIn("prefix72_pair", {record["name"] for record in records})

    def test_memory_probe_completes_for_a_fast_hash(self):
        params = {"iterations": 1000, "hash_len": 32, "salt_len": 16}
        hasher = make_hasher("pbkdf2_sha256", params)
        encoded = hasher.hash_password("synthetic-password")
        probed = probe_verify_rss("pbkdf2_sha256", params, "synthetic-password", encoded, timeout=60)
        self.assertTrue(probed["ok"])
        self.assertGreaterEqual(probed["peak_rss"], probed["baseline_rss"])

    def test_argon2_probe_reports_configured_memory(self):
        params = {"memory_kib": 19456, "time_cost": 2, "parallelism": 1, "hash_len": 32, "salt_len": 16}
        hasher = make_hasher("argon2id", params)
        encoded = hasher.hash_password("synthetic-password")
        probed = probe_verify_rss("argon2id", params, "synthetic-password", encoded, timeout=60)
        self.assertTrue(probed["ok"])
        self.assertGreater(probed["delta_rss"], 8 * 1024 * 1024)

    def test_memory_skip_rule(self):
        self.assertTrue(should_skip_for_memory(1000, 1000))
        self.assertFalse(should_skip_for_memory(0, 1000))
        self.assertFalse(should_skip_for_memory(100, 1000))


if __name__ == "__main__":
    unittest.main()
