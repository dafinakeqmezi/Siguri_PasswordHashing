"""Checks for the optional web login load test. These are not experimental results."""

import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

from password_benchmark.hashers import make_hasher
from password_benchmark.web_load import load_web_settings, parse_locust_stats

FAST_BCRYPT = {"cost": 4}


class WebSettingsTests(unittest.TestCase):
    def test_settings_are_separate_from_the_declared_designs(self):
        settings = load_web_settings()
        self.assertEqual(settings["algorithms"], ["argon2id", "bcrypt", "pbkdf2_sha256", "scrypt"])
        self.assertIn(4, settings["clients"])
        self.assertEqual(len(settings["sha256"]), 64)

    def test_locust_statistics_are_parsed_by_request_kind(self):
        header = '"Type","Name","Request Count","Failure Count","Median Response Time","Average Response Time","Min Response Time","Max Response Time","Average Content Size","Requests/s","Failures/s","50%","66%","75%","80%","90%","95%","98%","99%","99.9%","99.99%","100%"\n'
        rows = (
            '"POST","/login","90","0","48","50","40","80","11","3.0","0.0","48","50","52","53","60","70","75","78","80","80","80"\n'
            '"POST","/login wrong","10","1","47","49","40","70","40","0.33","0.03","47","48","50","51","55","65","70","70","70","70","70"\n'
            '"","Aggregated","100","1","48","50","40","80","14","3.33","0.03","48","50","52","53","60","69","74","78","80","80","80"\n'
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run_stats.csv"
            path.write_text(header + rows, encoding="utf-8")
            stats = parse_locust_stats(path)
        self.assertEqual(set(stats), {"correct", "wrong", "all"})
        self.assertEqual(stats["correct"]["p95_ms"], 70.0)
        self.assertEqual(stats["wrong"]["failures"], 1)
        self.assertEqual(stats["all"]["requests_per_second"], 3.33)


@unittest.skipUnless(find_spec("fastapi") and find_spec("httpx"), "optional web packages are not installed")
class WebAppTests(unittest.TestCase):
    def test_login_accepts_the_stored_password_only(self):
        from fastapi.testclient import TestClient

        from password_benchmark.web_app import create_app

        hasher = make_hasher("bcrypt", FAST_BCRYPT)
        client = TestClient(create_app("bcrypt", FAST_BCRYPT, {"user000": hasher.hash_password("synthetic-password")}))
        self.assertEqual(client.get("/health").json(), {"algorithm": "bcrypt", "users": 1})
        self.assertEqual(client.post("/login", json={"username": "user000", "password": "synthetic-password"}).status_code, 200)
        self.assertEqual(client.post("/login", json={"username": "user000", "password": "synthetic-passwore"}).status_code, 401)
        self.assertEqual(client.post("/login", json={"username": "nobody", "password": "synthetic-password"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
