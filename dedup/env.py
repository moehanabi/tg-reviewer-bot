"""Dedup bot configuration (``DEDUP_*`` environment variables).

Kept separate from the main bot's ``env.py`` on purpose: the dedup bot is a
stand-alone process with its own token and database.

``DEDUP_REVIEWER_GROUP`` / ``DEDUP_MAIN_BOT_ID`` / ``DEDUP_BACKFILL_CHAT``
accept a comma-separated list of ids (one process watches several review
groups, recognising submissions from several main bots). A single plain value
-- the original form -- keeps working unchanged.
"""
import os


def _ids(raw):
    """Parse a comma-separated env value into a set of ints (empty -> empty set)."""
    if not raw or not raw.strip():
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


# --- long-running bot ---
DEDUP_TOKEN = os.environ.get("DEDUP_TOKEN")
DEDUP_CUSTOMAPI = os.environ.get("DEDUP_CUSTOMAPI", "https://api.telegram.org/bot")
# Review groups watched by this process (all share one global baseline).
DEDUP_REVIEWER_GROUPS = _ids(os.environ.get("DEDUP_REVIEWER_GROUP"))
# Author filter: only submissions sent by one of the configured main bots are
# recognised. Usually ``Bot.get_me().id``; may differ if a main bot has more
# than one account. Matching is cross-bot: content from any main bot is
# checked against everything in the baseline.
DEDUP_MAIN_BOT_IDS = _ids(os.environ.get("DEDUP_MAIN_BOT_ID"))

# --- shared ---
DEDUP_DB_URL = os.environ.get("DEDUP_DB_URL", "sqlite:///data/dedup.db")

# --- detection thresholds ---
# pHash Hamming distance: 0-5 same image, 5-15 similar, >15 different.
DEDUP_PHASH_THRESHOLD = int(os.getenv("DEDUP_PHASH_THRESHOLD", "8"))
# SimHash Hamming distance on the 64-bit fingerprint (~75% similar at 16).
DEDUP_SIMHASH_THRESHOLD = int(os.getenv("DEDUP_SIMHASH_THRESHOLD", "16"))
DEDUP_ENABLE_SIMHASH = os.getenv("DEDUP_ENABLE_SIMHASH", "True") == "True"
# SimHash on very short text is noisy; only approximate-match text of this
# length or longer (exact text_hash matching is unaffected).
DEDUP_MIN_SIMHASH_TEXT_LEN = int(os.getenv("DEDUP_MIN_SIMHASH_TEXT_LEN", "12"))

# --- one-shot Telethon backfill (user account) ---
# MTProto user session file (must be a member of the review group).
TG_USER_SESSION_FILE = os.environ.get("TG_USER_SESSION_FILE")
# api_id / api_hash, only needed to create the session file on first run.
TG_USER_API_ID = os.environ.get("TG_USER_API_ID")
TG_USER_API_HASH = os.environ.get("TG_USER_API_HASH")
# The review group(s) to backfill (= DEDUP_REVIEWER_GROUP). One-shot runs
# iterate over all of them; each group's resume checkpoint is independent.
DEDUP_BACKFILL_CHATS = _ids(os.environ.get("DEDUP_BACKFILL_CHAT"))
