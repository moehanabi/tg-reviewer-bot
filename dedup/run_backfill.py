"""Entry point for the one-shot historical backfill (Telethon user account).

Run with ``python -m dedup.run_backfill`` (or ``python dedup/run_backfill.py``).

First run logs in interactively (phone + code, then 2FA password if the account
has it) and creates the session file; every later run just connects and resumes
from the saved auth + the ``backfill_state`` checkpoint.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make ``dedup.*`` importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telethon import TelegramClient

from dedup.backfill import backfill
from dedup.env import (
    DEDUP_BACKFILL_CHATS,
    DEDUP_MAIN_BOT_IDS,
    TG_USER_API_ID,
    TG_USER_API_HASH,
    TG_USER_SESSION_FILE,
)

logger = logging.getLogger("dedup.run_backfill")


def _make_client():
    """Telethon client on the user-account session.

    ``api_id`` / ``api_hash`` are only needed to *create* the session file on
    first login; once it exists, the bare session file is enough.
    """
    if TG_USER_API_ID and TG_USER_API_HASH:
        return TelegramClient(TG_USER_SESSION_FILE, int(TG_USER_API_ID), TG_USER_API_HASH)
    return TelegramClient(TG_USER_SESSION_FILE)


async def _authenticate(client):
    """Connect; on first run do the interactive phone/code login."""
    if client.is_user_authorized():
        return
    phone = input("Telegram phone number (e.g. +81...): ").strip()
    await client.sign_in(phone)  # sends the verification code
    code = input("Verification code: ").strip()
    try:
        await client.sign_in(phone, code)
    except Exception:  # 2FA password flow
        password = input("2FA password: ").strip()
        await client.sign_in(phone, code, password=password)
    logger.info("logged in and saved session to %s", TG_USER_SESSION_FILE)


async def _main(limit=None):
    if not DEDUP_BACKFILL_CHATS:
        raise SystemExit(
            "DEDUP_BACKFILL_CHAT is not set (comma-separated chat ids)"
        )
    if not DEDUP_MAIN_BOT_IDS:
        raise SystemExit("DEDUP_MAIN_BOT_ID is not set (comma-separated bot user ids)")
    client = _make_client()
    async with client:  # connect + disconnect
        await _authenticate(client)
        # ``limit`` applies per chat (each chat's checkpoint is independent,
        # so a resume continues each one below its own oldest processed id).
        for chat_id in sorted(DEDUP_BACKFILL_CHATS):
            logger.info("backfilling chat %s (limit=%s)", chat_id, limit)
            await backfill(client, chat_id, limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-shot review-group backfill.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="process at most this many submissions this run (resume continues below it)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    asyncio.run(_main(limit=args.limit))
