"""Content fingerprints for the dedup bot.

Low-level, DB-agnostic primitives:

- ``compute_phash``  -- perceptual hash (pHash) for images, 64-bit hex.
- ``sha256_bytes``   -- byte SHA-256 (content_hash for media / text_hash).
- ``simhash_text``   -- char n-gram SimHash, 64-bit hex (CJK friendly).
- ``hamming``        -- Hamming distance between two hex fingerprints.
- ``popcount64``     -- vectorised Hamming popcount over a NumPy int64 array.

The baseline-compare logic that consumes these lives in :mod:`dedup.detect`.
"""
import hashlib
import io

import imagehash
import numpy as np
from PIL import Image

# 8-bit popcount lookup used by :func:`popcount64`.
_POPCOUNT8 = np.array([bin(i).count("1") for i in range(256)], dtype=np.int8)


def compute_phash(img_bytes: bytes) -> str:
    """Perceptual hash (pHash) of an image, as a 16-char (64-bit) hex string.

    Robust to recompression / resizing / quality changes, which is what we
    need to catch a "re-encoded" duplicate of an image.
    """
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")
    return str(imagehash.phash(img))


def sha256_bytes(b: bytes) -> str:
    """Byte-level SHA-256 hex digest (content_hash / text_hash)."""
    return hashlib.sha256(b).hexdigest()


def simhash_text(text: str, n: int = 4, bits: int = 64) -> str:
    """Char n-gram SimHash of ``text`` as a 64-bit hex string.

    Char n-grams (not word n-grams) make it CJK-friendly. We normalise by
    lower-casing and dropping whitespace so minor case / spacing / pangu
    spacing differences still collapse to a comparable fingerprint.
    """
    if not text:
        return "0" * (bits // 4)
    text = "".join(text.lower().split())
    if not text:
        return "0" * (bits // 4)

    v = [0] * bits
    count = max(1, len(text) - n + 1)
    for i in range(count):
        gram = text[i : i + n]
        h = int.from_bytes(hashlib.sha1(gram.encode("utf-8")).digest()[: bits // 8], "big")
        for j in range(bits):
            v[j] += 1 if (h >> j) & 1 else -1

    out = 0
    for j in range(bits):
        if v[j] > 0:
            out |= 1 << j
    return format(out, "016x")


def hamming(hex_a: str, hex_b: str) -> int:
    """Hamming distance between two hex strings of arbitrary length."""
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")


def popcount64(x: np.ndarray) -> np.ndarray:
    """Per-element Hamming popcount of a uint64 array (fully vectorised).

    ``popcount64(arr ^ query)`` gives the Hamming distance of every baseline
    entry against ``query`` in one pass.
    """
    x = x.astype(np.uint64)
    return (
        _POPCOUNT8[x & 0xFF]
        + _POPCOUNT8[(x >> 8) & 0xFF]
        + _POPCOUNT8[(x >> 16) & 0xFF]
        + _POPCOUNT8[(x >> 24) & 0xFF]
        + _POPCOUNT8[(x >> 32) & 0xFF]
        + _POPCOUNT8[(x >> 40) & 0xFF]
        + _POPCOUNT8[(x >> 48) & 0xFF]
        + _POPCOUNT8[(x >> 56) & 0xFF]
    )
