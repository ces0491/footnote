"""Seed derivation.

Every random stream is derived from a root seed and a path of labels, hashed
with BLAKE2b so the result doesn't depend on Python's per-process string hash.
The same (seed, labels) always gives the same stream.
"""

from __future__ import annotations

import hashlib

import numpy as np


def derive_seed(*parts: object) -> int:
    h = hashlib.blake2b(digest_size=8)
    for part in parts:
        h.update(repr(part).encode("utf-8"))
        h.update(b"\x1f")
    return int.from_bytes(h.digest(), "little")


def make_rng(*parts: object) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(derive_seed(*parts)))
