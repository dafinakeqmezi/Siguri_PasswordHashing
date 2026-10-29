"""Locust clients for the optional login load test. Started by web_load.py, not imported by it.

Each client logs in as a random synthetic user with no wait between requests.
A configured share of requests sends a wrong password, which must return 401.
"""

import json
import os
import random
from pathlib import Path

from locust import HttpUser, constant, task

CLIENT = json.loads(Path(os.environ["WEB_LOGIN_CLIENT_FILE"]).read_text(encoding="utf-8"))


class LoginClient(HttpUser):
    wait_time = constant(0)

    @task
    def login(self) -> None:
        user = random.choice(CLIENT["users"])
        wrong = random.random() < CLIENT["wrong_password_fraction"]
        password = user["wrong_password"] if wrong else user["password"]
        expected = 401 if wrong else 200
        name = "/login wrong" if wrong else "/login"
        with self.client.post(
            "/login", json={"username": user["username"], "password": password}, name=name, catch_response=True
        ) as response:
            if response.status_code == expected:
                response.success()
            else:
                response.failure(f"expected {expected}, got {response.status_code}")
