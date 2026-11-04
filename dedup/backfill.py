"""One-shot historical backfill (Telethon user account).

Bot API has no history-read API, so this runs the MTProto *user* protocol:
read the review-group history (newest -> oldest), fingerprint each submission
the same way the live bot does, and write first-occurrence rows into
``submission_contents``. Resumable via ``backfill_state.last_min_message_id``
(re-running over an already-processed range is a no-op: ``record_items``
ignores the unique-index collision).
"""
import asyncio
import io
import logging
import time

from dedup.db import get_checkpoint, record_items, set_checkpoint
from dedup.env import DEDUP_MAIN_BOT_IDS
from dedup.fingerprint import compute_phash, sha256_bytes, simhash_text

logger = logging.getLogger("dedup.backfill")

# Checkpoint every this many submissions (the per-row unique index makes
# re-processing on resume a no-op, so a coarse checkpoint is safe).
BATCH_SIZE = 50


def _sender_user_id(message):
    """The numeric user id of the sender, or None (not a user)."""
    sid = message.sender_id
    return getattr(sid, "user_id", None) if sid is not None else None


async def _download(client, message, retries=3):
    """Download a message's primary media to bytes, retrying transient errors.

    Telethon already auto-sleeps/retries on ``FloodWaitError``; this retries
    the rest (network blips) a few times before giving up.
    """
    buf = io.BytesIO()
    last_err = None
    for attempt in range(retries):
        try:
            await client.download_media(message, file=buf)
            return buf.getvalue()
        except Exception as e:  # noqa: BLE001 - retry, then re-raise
            last_err = e
            buf = io.BytesIO()
            await asyncio.sleep(1 + attempt)
    raise last_err


async def _fingerprint_items(client, message):
    """The fingerprintable pieces of one submission message (Telethon-side).

    Mirrors :func:`dedup.bot._build_items`, but with Telethon media access.
    """
    items = []
    # media? (Telethon has no separate ``.animation`` -- GIFs come as a document)
    if not (message.photo or message.video or message.sticker or message.document):
        # pure-text submission: text dedup applies only here. A media
        # message's caption does not participate in the text baseline.
        text = message.text
        if text:
            items.append({
                "type": "text",
                "text_hash": sha256_bytes(text.encode("utf-8")),
                "text_simhash": simhash_text(text),
            })
        return items
    data = await _download(client, message)
    if message.photo:
        items.append({"type": "photo", "phash": compute_phash(data)})
    elif message.sticker:
        items.append({"type": "sticker", "content_hash": sha256_bytes(data)})
    elif message.video:
        items.append({"type": "video", "content_hash": sha256_bytes(data)})
    else:  # document (GIFs land here)
        items.append({"type": "document", "content_hash": sha256_bytes(data)})
    return items


def _row(message, item, key):
    return {
        "submission_key": key,
        "type": item["type"],
        "phash": item.get("phash"),
        "content_hash": item.get("content_hash"),
        "text_hash": item.get("text_hash"),
        "text_simhash": item.get("text_simhash"),
        # The user account cannot read ``file_unique_id`` (a Bot API concept) --
        # it stays NULL here; the byte ``content_hash`` dedups across both sides.
        "file_unique_id": None,
        "source_chat_id": message.chat_id,
        "source_message_id": message.id,
        "submitter_id": None,
        "first_seen_date": message.date,
    }


async def backfill(client, chat, limit=None):
    """Read review-group history (newest -> oldest) and write first-occurrence rows.

    ``chat`` is the review-group id; ``limit`` bounds how many submissions to
    process this run (for a quick ``--limit`` smoke test). Resumes from
    ``backfill_state.last_min_message_id``.
    """
    checkpoint = get_checkpoint(chat)
    batch = []
    saved_rows = 0
    last_id = checkpoint
    start = time.time()

    async def _flush(mid):
        nonlocal batch, last_id
        if not batch:
            return
        record_items(batch)
        batch.clear()
        last_id = mid
        set_checkpoint(chat, last_id)

    # ``max_id`` excludes id >= checkpoint, so on resume we continue below the
    # oldest id we already processed. First run (checkpoint None) has no bound.
    kwargs = {"max_id": checkpoint} if checkpoint is not None else {}
    async for message in client.iter_messages(chat, **kwargs):
        if limit is not None and saved_rows >= limit:
            break
        last_id = message.id
        # Mirror the live bot: content posts are top-level only; replies and
        # review messages (vote buttons) are operational, not submissions.
        if (
            _sender_user_id(message) not in DEDUP_MAIN_BOT_IDS
            or message.is_reply
            or message.buttons
        ):
            continue
        try:
            items = await _fingerprint_items(client, message)
        except Exception as e:  # noqa: BLE001 - one bad message must not kill the run
            logger.warning("skip message %s: %s", message.id, e)
            continue
        if not items:
            continue
        key = str(message.id)
        for item in items:
            batch.append(_row(message, item, key))
        saved_rows += 1
        if saved_rows % BATCH_SIZE == 0:
            await _flush(message.id)
            logger.info(
                "backfilled %d submissions (last msg %d, %.0fs)",
                saved_rows, message.id, time.time() - start,
            )

    await _flush(last_id)
    logger.info("backfill done: %d submissions this run", saved_rows)
