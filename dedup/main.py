"""Entry point for the long-running dedup bot.

Run with ``python -m dedup.main`` (or ``python dedup/main.py``).
"""
import logging
import sys
from pathlib import Path

# Make ``dedup.*`` importable when run as a plain script (``python dedup/main.py``).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram.ext import ApplicationBuilder, MessageHandler, filters

from dedup.bot import load_baseline, on_new_message
from dedup.env import (
    DEDUP_CUSTOMAPI,
    DEDUP_MAIN_BOT_IDS,
    DEDUP_REVIEWER_GROUPS,
    DEDUP_TOKEN,
)

logger = logging.getLogger("dedup.main")


async def on_init(application):
    load_baseline()
    for chat_id in DEDUP_REVIEWER_GROUPS:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text="🥷查重 bot 上线🥷",
            )
        except Exception:  # bot removed from / cannot post in this group:
            # log and keep going -- the other groups must still be served.
            logger.exception("online notice to chat %s failed", chat_id)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Fail fast with a clear message on missing config (an empty id set would
    # otherwise silently match nothing; today a missing group id crashes here
    # anyway and a missing main-bot id only crashes on the first message).
    if not DEDUP_REVIEWER_GROUPS:
        raise SystemExit("DEDUP_REVIEWER_GROUP is not set (comma-separated group ids)")
    if not DEDUP_MAIN_BOT_IDS:
        raise SystemExit("DEDUP_MAIN_BOT_ID is not set (comma-separated bot user ids)")
    application = (
        ApplicationBuilder()
        .token(DEDUP_TOKEN)
        .base_url(DEDUP_CUSTOMAPI)
        .job_queue(None)
        .get_updates_connect_timeout(60)
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .get_updates_read_timeout(60)
        .get_updates_write_timeout(60)
        .post_init(on_init)
        .build()
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGES
            & filters.Chat(chat_id=DEDUP_REVIEWER_GROUPS),
            on_new_message,
        )
    )
    application.run_polling()
