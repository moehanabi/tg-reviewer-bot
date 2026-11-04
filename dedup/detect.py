"""Baseline compare: keep the photo pHash / text SimHash fingerprints in
memory (as int lists -> NumPy) and find near matches for a new content item.

The baseline is loaded once at startup (:meth:`Baseline.load`) and grown as
the bot writes new first-occurrence rows. The vectorised Hamming-distance
scan makes "which baseline entries are within threshold" a single pass, so
~200k photos compare in a few milliseconds.
"""
import numpy as np

from dedup.db import (
    find_exact,
    load_file_unique_ids,
    load_photo_phashes,
    load_text_simhashes,
)
from dedup.env import (
    DEDUP_ENABLE_SIMHASH,
    DEDUP_MIN_SIMHASH_TEXT_LEN,
    DEDUP_PHASH_THRESHOLD,
    DEDUP_SIMHASH_THRESHOLD,
)
from dedup.fingerprint import popcount64


def _scan(query_int, ints, rows, threshold):
    """[(row, distance)] for every baseline entry within ``threshold``."""
    if not ints:
        return []
    mask = (1 << 64) - 1
    arr = np.array(ints, dtype=np.uint64) & np.uint64(mask)
    query_int &= mask
    dist = popcount64(arr ^ query_int)
    return [(rows[i], int(d)) for i, d in enumerate(dist) if d <= threshold]


def _dedup(matches):
    """Collapse matches to one per baseline row, keeping the smallest distance."""
    best = {}
    for row, d, kind in matches:
        k = row["id"]
        if k not in best or d < best[k][1]:
            best[k] = (row, d, kind)
    return list(best.values())


class Baseline:
    def __init__(self):
        self.photo_phashes = []  # ints, parallel to photo_rows
        self.photo_rows = []
        self.text_simhashes = []  # ints, parallel to text_rows
        self.text_rows = []
        self.fui_rows = {}  # file_unique_id -> earliest row (bot-side cache)

    def load(self):
        """Populate the in-memory structures from the database."""
        self.photo_rows = load_photo_phashes()
        self.photo_phashes = [int(r["phash"], 16) for r in self.photo_rows]
        self.text_rows = load_text_simhashes()
        self.text_simhashes = [int(r["text_simhash"], 16) for r in self.text_rows]
        self.fui_rows = {}
        for r in load_file_unique_ids():
            self.add_fui(r["file_unique_id"], r)

    def add_photo(self, phash_hex, row):
        self.photo_phashes.append(int(phash_hex, 16))
        self.photo_rows.append(row)

    def add_text_simhash(self, simhex, row):
        self.text_simhashes.append(int(simhex, 16))
        self.text_rows.append(row)

    def add_fui(self, fui, row):
        cur = self.fui_rows.get(fui)
        if cur is None or row["first_seen_date"] < cur["first_seen_date"]:
            self.fui_rows[fui] = row

    def find_matches(self, item):
        """Return de-duplicated ``[(row, distance, kind)]`` for one content item.

        ``kind`` is ``"phash"`` / ``"simhash"`` / ``"exact"`` and ``distance``
        is the Hamming distance (0 for an exact byte/hash hit).
        """
        raw = []
        t = item["type"]
        if t == "photo":
            if item.get("phash"):
                raw += [
                    (r, d, "phash")
                    for r, d in _scan(
                        int(item["phash"], 16),
                        self.photo_phashes,
                        self.photo_rows,
                        DEDUP_PHASH_THRESHOLD,
                    )
                ]
        elif t == "text":
            raw += [(r, 0, "exact") for r in find_exact("text_hash", item.get("text_hash"))]
            if (
                DEDUP_ENABLE_SIMHASH
                and item.get("text_simhash")
                and len(item.get("text", "")) >= DEDUP_MIN_SIMHASH_TEXT_LEN
            ):
                raw += [
                    (r, d, "simhash")
                    for r, d in _scan(
                        int(item["text_simhash"], 16),
                        self.text_simhashes,
                        self.text_rows,
                        DEDUP_SIMHASH_THRESHOLD,
                    )
                ]
        else:
            # video / gif / document / sticker: byte-exact only
            raw += [(r, 0, "exact") for r in find_exact("content_hash", item.get("content_hash"))]
        return _dedup(raw)
