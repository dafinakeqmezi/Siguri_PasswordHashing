"""Library wrappers. The benchmark times verify(), not these wrappers' construction."""

import base64
import hashlib
import hmac
import os

import bcrypt
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type, hash_secret, verify_secret


class Argon2idHasher:
    def __init__(self, memory_kib: int, time_cost: int, parallelism: int, hash_len: int, salt_len: int):
        if parallelism < 1:
            raise ValueError("Argon2id parallelism must be at least 1")
        if memory_kib < 8 * parallelism:
            raise ValueError("Argon2id memory_kib must be at least 8 * parallelism")
        if time_cost < 1 or hash_len < 16 or salt_len < 8:
            raise ValueError("Invalid Argon2id hash length, salt length, or time cost")
        self.memory_kib = int(memory_kib)
        self.time_cost = int(time_cost)
        self.parallelism = int(parallelism)
        self.hash_len = int(hash_len)
        self.salt_len = int(salt_len)

    def hash_password(self, password: str) -> str:
        encoded = hash_secret(
            secret=password.encode("utf-8"),
            salt=os.urandom(self.salt_len),
            time_cost=self.time_cost,
            memory_cost=self.memory_kib,
            parallelism=self.parallelism,
            hash_len=self.hash_len,
            type=Type.ID,
        )
        return encoded.decode("ascii")

    def verify(self, password: str, encoded: str) -> bool:
        try:
            verify_secret(encoded.encode("ascii"), password.encode("utf-8"), type=Type.ID)
        except VerifyMismatchError:
            return False
        return True


class BcryptHasher:
    def __init__(self, cost: int):
        if not 4 <= int(cost) <= 31:
            raise ValueError("bcrypt cost must be between 4 and 31")
        self.cost = int(cost)

    def hash_password(self, password: str) -> str:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=self.cost))
        return hashed.decode("ascii")

    def verify(self, password: str, encoded: str) -> bool:
        try:
            return bool(bcrypt.checkpw(password.encode("utf-8"), encoded.encode("ascii")))
        except ValueError:
            return False


class Pbkdf2Sha256Hasher:
    def __init__(self, iterations: int, hash_len: int, salt_len: int):
        if int(iterations) < 1 or int(hash_len) < 16 or int(salt_len) < 8:
            raise ValueError("Invalid PBKDF2 iterations, hash length, or salt length")
        self.iterations = int(iterations)
        self.hash_len = int(hash_len)
        self.salt_len = int(salt_len)

    def hash_password(self, password: str) -> str:
        salt = os.urandom(self.salt_len)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.iterations,
            dklen=self.hash_len,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        derived_b64 = base64.b64encode(derived).decode("ascii")
        return f"pbkdf2_sha256${self.iterations}${salt_b64}${derived_b64}"

    def verify(self, password: str, encoded: str) -> bool:
        parts = encoded.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            raise ValueError("Unrecognized PBKDF2 hash encoding")
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)


def make_hasher(algorithm: str, params: dict):
    if algorithm == "argon2id":
        return Argon2idHasher(
            memory_kib=params["memory_kib"],
            time_cost=params["time_cost"],
            parallelism=params["parallelism"],
            hash_len=params["hash_len"],
            salt_len=params["salt_len"],
        )
    if algorithm == "bcrypt":
        return BcryptHasher(cost=params["cost"])
    if algorithm == "pbkdf2_sha256":
        return Pbkdf2Sha256Hasher(
            iterations=params["iterations"],
            hash_len=params["hash_len"],
            salt_len=params["salt_len"],
        )
    raise ValueError(f"Unknown algorithm: {algorithm}")
