"""Dedup bot database (``dedup.db``), following the main bot's ``db_op.py`` style.

Two tables:

- ``submission_contents`` -- one row per unique piece of content in the
  review group (a photo / video / gif / document / sticker / text). This is
  the comparison baseline.
- ``backfill_state`` -- resume checkpoint for the Telethon backfill.
"""
import os
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Index,
    String,
    and_,
    create_engine,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from dedup.env import DEDUP_DB_URL


class Base(DeclarativeBase):
    pass


class SubmissionContent(Base):
    __tablename__ = "submission_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Grouping key for the submission (the main bot's first content message id).
    submission_key: Mapped[str] = mapped_column(String(190), nullable=False)
    # photo | video | gif | document | sticker | text
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    phash: Mapped[str] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    text_simhash: Mapped[str] = mapped_column(String(32), nullable=True)
    # Cache key: only filled by the Bot API side (the user account / backfill
    # cannot read file_unique_id, so it stays NULL there).
    file_unique_id: Mapped[str] = mapped_column(String(190), nullable=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    submitter_id: Mapped[str] = mapped_column(String(190), nullable=True)
    first_seen_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_pcid", "file_unique_id"),
        Index("idx_phash", "phash"),
        Index("idx_content", "content_hash"),
        Index("idx_text", "text_hash"),
        Index("idx_simhash", "text_simhash"),
        # A message can hold one media piece + one caption; make (chat, msg, type) unique
        # so re-running backfill / the bot does not create duplicate rows.
        Index(
            "idx_source", "source_chat_id", "source_message_id", "type", unique=True
        ),
    )

    def __repr__(self):
        return (
            f"SubmissionContent(key={self.submission_key}, type={self.type}, "
            f"msg={self.source_message_id}, first_seen={self.first_seen_date})"
        )


class BackfillState(Base):
    __tablename__ = "backfill_state"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # The oldest message id processed so far (resume pointer).
    last_min_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    last_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class DB:
    def __init__(self, database_url):
        if database_url.startswith("sqlite"):
            # File path is everything after "sqlite:///" -- a relative
            # (``sqlite:///data/dedup.db``) or absolute (``sqlite:////abs.db``)
            # path. Create its directory so the first connect can create the
            # file. In-memory (``sqlite:``) has no file to create.
            path = database_url.removeprefix("sqlite:///")
            if path:
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def select(self, table, *conditions):
        with self.Session.begin() as session:
            stmt = select("*").select_from(table)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            return session.execute(stmt).mappings().all()

    def insert(self, table, **kwargs):
        with self.Session.begin() as session:
            session.add(table(**kwargs))

    def update(self, table, condition_expr, **kwargs):
        with self.Session.begin() as session:
            stmt = update(table).where(condition_expr).values(**kwargs)
            session.execute(stmt)


db = DB(DEDUP_DB_URL)


def record_items(items):
    """Insert a list of ``SubmissionContent`` field-dicts.

    One short transaction per row so a single duplicate (the unique index
    ``(source_chat_id, source_message_id, type)``) does not poison the whole
    batch -- re-running the backfill over an already-processed range must be
    a no-op, not an error. The DB-generated ``id`` is written back into each
    dict, so callers can key the in-memory baseline by a stable value.
    """
    for it in items:
        try:
            with db.Session.begin() as session:
                obj = SubmissionContent(**it)
                session.add(obj)
                session.flush()
                session.refresh(obj)
                it["id"] = obj.id
        except IntegrityError:  # already recorded (re-run / concurrent insert)
            pass


def find_exact(column, value):
    """Rows matching a single exact hash column (``content_hash`` / ``text_hash``)."""
    return db.select(SubmissionContent, getattr(SubmissionContent, column) == value)


def load_photo_phashes():
    """All photo rows carrying a pHash (the baseline for the NumPy scan)."""
    return db.select(
        SubmissionContent,
        SubmissionContent.type == "photo",
        SubmissionContent.phash.isnot(None),
    )


def load_text_simhashes():
    """All text rows carrying a SimHash (the baseline for the SimHash scan)."""
    return db.select(
        SubmissionContent,
        SubmissionContent.type == "text",
        SubmissionContent.text_simhash.isnot(None),
    )


def load_file_unique_ids():
    """All rows that carry a ``file_unique_id`` (Bot-side cache)."""
    return db.select(SubmissionContent, SubmissionContent.file_unique_id.isnot(None))


def get_checkpoint(chat_id):
    rows = db.select(BackfillState, BackfillState.chat_id == chat_id)
    return rows[0]["last_min_message_id"] if rows else None


def set_checkpoint(chat_id, last_min_message_id, last_date=None):
    existing = db.select(BackfillState, BackfillState.chat_id == chat_id)
    if existing:
        db.update(
            BackfillState,
            BackfillState.chat_id == chat_id,
            last_min_message_id=last_min_message_id,
            last_date=datetime.now(),
        )
    else:
        db.insert(
            BackfillState,
            chat_id=chat_id,
            last_min_message_id=last_min_message_id,
            last_date=datetime.now(),
        )
