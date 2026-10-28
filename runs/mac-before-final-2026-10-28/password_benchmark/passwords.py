"""Seeded synthetic passwords. The same seed always produces the same corpus."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticPassword:
    password_id: int
    password: str
    char_length: int
    byte_length: int


def generate_passwords(count: int, lengths: list[int], charset: str, seed: int) -> list[SyntheticPassword]:
    rng = random.Random(seed)
    passwords = []
    for password_id in range(count):
        length = lengths[password_id % len(lengths)]
        password = "".join(rng.choice(charset) for _ in range(length))
        passwords.append(
            SyntheticPassword(
                password_id=password_id,
                password=password,
                char_length=length,
                byte_length=len(password.encode("utf-8")),
            )
        )
    return passwords
