"""Duplicate-submission detector for the review group.

Physical isolation from the main bot: this package has its own env vars
(``DEDUP_*``), its own database (``DEDUP_DB_URL``) and its own Telegram
credentials. Run the long-running bot with ``python -m dedup.main`` and the
one-shot historical backfill with ``python -m dedup.run_backfill``.
"""
