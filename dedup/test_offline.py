"""Offline P5 verification harness -- no Telegram, no network.

Exercises :mod:`fingerprint` + :mod:`db` + :mod:`detect` against a throwaway
SQLite DB with synthetic images/text, replaying the *decision* the live bot
makes per content item (``detect -> mark / store``):

- repeat image     : 1st time no mark (stored), 2nd time mark (distance 0)
- recompressed image: mark (pHash within threshold)
- different image  : no mark
- SimHash text     : exact repeat + minor edit -> mark, different -> no mark
- byte hash (video)  : exact repeat -> mark, different -> no mark

Run with:  ``python dedup/test_offline.py``
"""
import io
import os
import sys
import tempfile
from datetime import datetime
from itertools import count

# Point the DB at a throwaway file BEFORE importing ``dedup.db`` (which builds
# the engine on import) and before ``dedup.detect``.
_db = os.path.join(tempfile.mkdtemp(), "dedup.db")
os.environ["DEDUP_DB_URL"] = f"sqlite:///{_db}"
os.environ.setdefault("DEDUP_REVIEWER_GROUP", "-100")
os.environ.setdefault("DEDUP_MAIN_BOT_ID", "12345")
os.environ.setdefault("DEDUP_BACKFILL_CHAT", "-100")
os.environ.setdefault("DEDUP_TOKEN", "123:ABC")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from dedup.db import record_items  # noqa: E402
from dedup.detect import Baseline  # noqa: E402
from dedup.env import DEDUP_PHASH_THRESHOLD, DEDUP_SIMHASH_THRESHOLD  # noqa: E402
from dedup.fingerprint import (  # noqa: E402
    compute_phash,
    hamming,
    sha256_bytes,
    simhash_text,
)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name: <26}{detail}")


def _img_circle():
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    ImageDraw.Draw(img).ellipse([60, 60, 140, 140], fill=(200, 0, 0))
    return img


def _img_square():
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([40, 40, 160, 160], fill=(0, 0, 200))
    return img


def _png(img):
    b = io.BytesIO()
    img.convert("RGB").save(b, format="PNG")
    return b.getvalue()


def _recompress(img, quality=90):
    b = io.BytesIO()
    img.convert("RGB").save(b, format="JPEG", quality=quality)
    return b.getvalue()


class Flow:
    """Mirrors :func:`dedup.bot.on_new_message` per-item: detect, then mark or store."""

    def __init__(self):
        self.baseline = Baseline()
        self._next_msg = count(1)

    def process(self, item, chat=-100):
        hits = self.baseline.find_matches(item)
        if hits:
            return hits
        row = {
            "submission_key": "test",
            "type": item["type"],
            "phash": item.get("phash"),
            "content_hash": item.get("content_hash"),
            "text_hash": item.get("text_hash"),
            "text_simhash": item.get("text_simhash"),
            "file_unique_id": None,
            "source_chat_id": chat,
            "source_message_id": next(self._next_msg),
            "submitter_id": None,
            "first_seen_date": datetime.now(),
        }
        record_items([row])  # persist (also proves the unique index works)
        if item["type"] == "photo":
            self.baseline.add_photo(row["phash"], row)
        elif item["type"] == "text":
            self.baseline.add_text_simhash(row["text_simhash"], row)
        return []


def _photo_item(png_bytes):
    return {"type": "photo", "phash": compute_phash(png_bytes)}


def _text_item(text):
    return {"type": "text", "text": text,
            "text_hash": sha256_bytes(text.encode("utf-8")),
            "text_simhash": simhash_text(text)}


def _media_item(bytestring):
    return {"type": "video", "content_hash": sha256_bytes(bytestring)}


def main():
    print("P5 offline verification (fingerprint + db + detect)\n")
    flow = Flow()

    # --- photos (pHash, in-memory scan) ---
    a_png = _png(_img_circle())
    a_jpg = _recompress(_img_circle())  # q=90 re-encode
    b_png = _png(_img_square())  # different image

    check("photo repeat: 1st no mark",
          not flow.process(_photo_item(a_png)),
          f"(baseline empty)")
    hits = flow.process(_photo_item(a_png))
    check("photo repeat: 2nd mark",
          bool(hits) and hits[0][1] == 0,
          f"(distance {hits[0][1] if hits else '?'})")
    hits = flow.process(_photo_item(a_jpg))
    check("photo recompressed: mark",
          bool(hits) and hits[0][1] <= DEDUP_PHASH_THRESHOLD,
          f"(distance {hits[0][1] if hits else '?'} <= {DEDUP_PHASH_THRESHOLD})")
    check("photo different: no mark", not flow.process(_photo_item(b_png)))

    # --- text (exact text_hash + SimHash) ---
    t1 = "今天的天气真不错，适合出去散步呢"
    t2 = "今天的天气真不错适合出去散步呢"  # minor edit (punct), similar
    t3 = "完全不一样的另一段测试文本"  # unrelated
    check("text: first store no mark", not flow.process(_text_item(t1)))
    hits = flow.process(_text_item(t1))
    check("text: exact repeat mark", bool(hits))
    hits = flow.process(_text_item(t2))
    check("text: similar edit mark",
          bool(hits) and hits[0][1] <= DEDUP_SIMHASH_THRESHOLD,
          f"(distance {hits[0][1] if hits else '?'})")
    check("text: different no mark", not flow.process(_text_item(t3)))

    # --- video / byte hash (exact) ---
    va, vb = b"fake-video-bytes-A", b"fake-video-bytes-B"
    check("video: first store no mark", not flow.process(_media_item(va)))
    check("video: exact repeat mark", bool(flow.process(_media_item(va))))
    check("video: different no mark", not flow.process(_media_item(vb)))

    # --- fresh baseline reloads from the DB and still matches ---
    fresh = Baseline()
    fresh.load()
    hits = fresh.find_matches(_photo_item(a_png))
    check("reload: photo still matches", bool(hits))
    hits = fresh.find_matches(_media_item(va))
    check("reload: video still matches", bool(hits))

    # --- hamming: scalar vs vectorised popcount agree ---
    import numpy as np

    from dedup.fingerprint import popcount64
    h = "123456789abcdef0"
    check("popcount64 == hamming",
          int(popcount64(np.array([int(h, 16) ^ int("0" * 16, 16)]))[0])
          == hamming(h, "0" * 16))

    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
