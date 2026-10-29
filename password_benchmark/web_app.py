"""Minimal FastAPI login service for the optional end-to-end load test.

The service stores only hashes of the synthetic corpus, held in memory. It is
a measurement target, not an example of a production login: it has no rate
limiting, sessions, or persistence.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from password_benchmark.hashers import make_hasher


class LoginRequest(BaseModel):
    username: str
    password: str


def create_app(algorithm: str, params: dict, stored: dict[str, str]) -> FastAPI:
    hasher = make_hasher(algorithm, params)
    app = FastAPI(title="Synthetic login benchmark")

    @app.get("/health")
    def health() -> dict:
        return {"algorithm": algorithm, "users": len(stored)}

    # A plain `def` endpoint runs in FastAPI's thread pool, so verifications overlap.
    @app.post("/login")
    def login(request: LoginRequest) -> dict:
        encoded = stored.get(request.username)
        if encoded is None or not hasher.verify(request.password, encoded):
            raise HTTPException(status_code=401, detail="invalid credentials")
        return {"ok": True}

    return app


def app_from_env() -> FastAPI:
    """Factory for `uvicorn --factory`. The runner writes the server file before starting the server."""
    spec = json.loads(Path(os.environ["WEB_LOGIN_SERVER_FILE"]).read_text(encoding="utf-8"))
    return create_app(spec["algorithm"], spec["params"], spec["stored"])
