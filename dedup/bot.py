"""Long-running dedup bot: watch the review group, and when a new submission
comes in, check it against the baseline and reply with a ``⚠️`` mark on a hit.

Submission anchor (see PLAN §2/§11): a content message is sent by one of the
main bots (``DEDUP_MAIN_BOT_IDS``), is media or plain text, and has no inline
keyboard (review messages carry the vote keyboard). L0 = mark only, never
block. All configured review groups share one in-memory baseline: matching is
cross-bot and cross-group, and a mark may reference content first seen in a
different group.

Non-submission main-bot messages are excluded structurally: real content posts
always arrive top-level (``send_submission`` never replies), while every
operational notice (review-meta / vote feedback / ``/append`` replies / ban
output) is a *reply* -- so any main-bot message with ``reply_to_message`` is
not a submission.
"""
import io
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from dedup.db import record_items
from dedup.detect import Baseline
from dedup.env import (
    DEDUP_MAIN_BOT_IDS,
    DEDUP_PHASH_THRESHOLD,
    DEDUP_REVIEWER_GROUPS,
    DEDUP_SIMHASH_THRESHOLD,
)
from dedup.fingerprint import compute_phash, sha256_bytes, simhash_text

logger = logging.getLogger("dedup.bot")

# Single in-memory baseline shared by every handler invocation.
baseline = Baseline()


def load_baseline():
    """Populate ``baseline`` from the database (call once on startup)."""
    baseline.load()
    return baseline


def _is_submission_message(message):
    if message.from_user is None or message.from_user.id not in DEDUP_MAIN_BOT_IDS:
        return False
    # Operational notices (review-meta, vote feedback, ...) are replies by the
    # main bot; real content is always posted top-level, never as a reply.
    if message.reply_to_message is not None:
        return False
    # Review messages carry the vote inline keyboard; content messages don't.
    if message.reply_markup is not None:
        return False
    return True


def _build_items(message):
    """The fingerprintable content pieces of one submission message."""
    items = []
    if message.photo:
        # ``message.photo`` is a *tuple* of PhotoSize (sizes), not a single
        # object -- pick the largest to download for the pHash.
        size = max(message.photo, key=lambda p: p.file_size)
        items.append({"type": "photo", "file_id": size.file_id,
                       "fui": size.file_unique_id})
    elif message.video:
        items.append({"type": "video", "file_id": message.video.file_id,
                       "fui": message.video.file_unique_id})
    elif message.animation:  # GIF
        items.append({"type": "gif", "file_id": message.animation.file_id,
                       "fui": message.animation.file_unique_id})
    elif message.sticker:
        items.append({"type": "sticker", "file_id": message.sticker.file_id,
                       "fui": message.sticker.file_unique_id})
    elif message.document:
        items.append({"type": "document", "file_id": message.document.file_id,
                       "fui": message.document.file_unique_id})
    # Text dedup applies to pure-text submissions only: a media message's
    # caption is neither checked nor stored (media posts do not participate
    # in the text baseline).
    if not items and (message.caption or message.text):
        items.append({"type": "text", "text": message.caption or message.text})
    return items


async def _download_file(context, file_id):
    file = await context.bot.get_file(file_id)
    buf = io.BytesIO()
    await file.download_to_memory(out=buf)
    return buf.getvalue()


def _message_link(chat_id, message_id):
    """t.me deep link to one message of a supergroup/channel, else None.

    Private-supergroup links use the bare chat id (``-100`` prefix stripped);
    basic groups / private chats have no public deep link, so the caller
    falls back to the plain ``消息 #id`` reference.
    """
    s = str(chat_id)
    if not s.startswith("-100") or not s[4:].isdigit():
        return None
    return f"https://t.me/c/{s[4:]}/{message_id}"


def _make_mark(matches):
    earliest = min(matches, key=lambda m: m[0]["first_seen_date"])
    row, dist, kind = earliest
    sim = 100 - dist / 64 * 100
    label = {"phash": "pHash", "simhash": "SimHash", "exact": "精确",
             "file_id": "文件"}.get(kind, kind)
    threshold = {"phash": DEDUP_PHASH_THRESHOLD,
                 "simhash": DEDUP_SIMHASH_THRESHOLD}.get(kind)
    thr = f"/ 阈值 {threshold}" if threshold is not None else ""
    first_seen = row["first_seen_date"]
    first_seen = first_seen.strftime("%Y-%m-%d %H:%M") if hasattr(first_seen, "strftime") else str(first_seen)
    ref = f"消息 #{row['source_message_id']}"
    link = _message_link(row["source_chat_id"], row["source_message_id"])
    if link:  # HTML parse mode: the id becomes a clickable jump to the original
        ref = f'<a href="{link}">{ref}</a>'
    return (
        f"⚠️ 疑似重复（相似度 {sim:.0f}%）\n"
        f"与早前投稿内容相似（{label} 距离 {dist}{thr}）\n"
        f"首次出现：{first_seen}（{ref}）"
    )


async def on_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only brand-new messages carry ``update.message``; edited messages /
    # channel posts arrive with it None (the filter matches them too) and
    # must not be re-fingerprinted -- an edit would match its own stored row.
    message = update.message
    if message is None or not _is_submission_message(message):
        return
    if message.chat.id not in DEDUP_REVIEWER_GROUPS:
        return

    items = _build_items(message)
    if not items:
        return

    now = datetime.now()
    key = str(message.media_group_id or message.message_id)
    new_rows = []
    matches = []

    for item in items:
        store_row = None
        try:
            if item["type"] == "text":
                item["text_hash"] = sha256_bytes(item["text"].encode("utf-8"))
                item["text_simhash"] = simhash_text(item["text"])
                hits = baseline.find_matches(item)
            elif item["fui"] in baseline.fui_rows:
                # Fast path: this exact file is already in the baseline.
                hits = [(baseline.fui_rows[item["fui"]], 0, "file_id")]
            else:
                data = await _download_file(context, item["file_id"])
                if item["type"] == "photo":
                    item["phash"] = compute_phash(data)
                else:
                    item["content_hash"] = sha256_bytes(data)
                hits = baseline.find_matches(item)
        except Exception as e:  # download / fingerprint failure: skip this piece
            logger.warning("skip item (download/fingerprint failed): %s", e)
            continue

        if hits:
            matches.extend(hits)
        else:
            store_row = {
                "submission_key": key,
                "type": item["type"],
                "phash": item.get("phash"),
                "content_hash": item.get("content_hash"),
                "text_hash": item.get("text_hash"),
                "text_simhash": item.get("text_simhash"),
                "file_unique_id": item.get("fui") if item["type"] != "text" else None,
                "source_chat_id": message.chat.id,
                "source_message_id": message.message_id,
                "submitter_id": None,
                "first_seen_date": now,
            }
            new_rows.append(store_row)

        # remember file_unique_id -> earliest row for the download fast path
        if item["type"] != "text":
            if item["fui"] not in baseline.fui_rows:
                earliest_row = (
                    min(hits, key=lambda m: m[0]["first_seen_date"])[0]
                    if hits
                    else store_row
                )
                baseline.add_fui(item["fui"], earliest_row)

    if new_rows:
        record_items(new_rows)
        for row in new_rows:
            if row["type"] == "photo":
                baseline.add_photo(row["phash"], row)
            elif row["type"] == "text":
                baseline.add_text_simhash(row["text_simhash"], row)

    if matches:
        await message.reply_text(_make_mark(matches), parse_mode="HTML")
