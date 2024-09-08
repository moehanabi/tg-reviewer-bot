import os
from datetime import datetime

from sqlalchemy import (
    DateTime,
    String,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from typing_extensions import Annotated

from src.config import Config


class Base(DeclarativeBase):
    pass


id_pk = Annotated[str, mapped_column(String(50), primary_key=True)]
id = Annotated[str, mapped_column(String(50), primary_key=True)]


class Submitter(Base):
    __tablename__ = "submitters"
    user_id: Mapped[id_pk]
    submission_count: Mapped[int]
    approved_count: Mapped[int]
    rejected_count: Mapped[int]

    def __repr__(self):
        return f"Submitter(User ID: {self.user_id}, Submission Count: {self.submission_count}, Approved Count: {self.approved_count}, Rejected Count: {self.rejected_count})"

    @staticmethod
    def count_increase(user_id, column_name, num=1):
        # check submitter exist or not first
        if not db.select(Submitter, Submitter.user_id == user_id):
            db.insert(
                Submitter,
                user_id=user_id,
                submission_count=0,
                approved_count=0,
                rejected_count=0,
            )
        current_count = db.select_column(
            Submitter, column_name, Submitter.user_id == user_id
        )
        db.update(
            Submitter,
            Submitter.user_id == user_id,
            **{column_name: current_count + num},
        )

    @staticmethod
    def get_submitters():
        return db.select(Submitter)

    @staticmethod
    def get_submitter(user_id):
        try:
            return db.select(Submitter, Submitter.user_id == user_id)[0]
        except IndexError:
            print(f"IndexError: Submitter {user_id} not found")
            return None


class Banned_user(Base):
    __tablename__ = "banned_users"
    user_id: Mapped[id_pk]
    user_name: Mapped[str] = mapped_column(String(50), nullable=True)
    user_fullname: Mapped[str] = mapped_column(String(50), nullable=True)
    banned_reason: Mapped[str] = mapped_column(String(50), nullable=True)
    banned_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    banned_by: Mapped[id]

    def __repr__(self):
        return f"Banned_user({self.user_fullname} ({f'@{self.user_name}, ' if self.user_name else ''}{self.user_id}), Banned Date: {self.banned_date}, Banned By: {self.banned_by}), Reason: {self.banned_reason})"

    @staticmethod
    def ban_user(
            user_id, user_name, user_fullname, banned_by, banned_reason=None
    ):
        try:
            db.insert(
                Banned_user,
                user_id=user_id,
                user_name=user_name,
                user_fullname=user_fullname,
                banned_by=banned_by,
                banned_reason=banned_reason,
            )
        except IntegrityError as e:
            print(f"IntegrityError: {e}")

    @staticmethod
    def is_banned(user_id):
        return bool(db.select(Banned_user, Banned_user.user_id == user_id))

    @staticmethod
    def unban_user(user_id):
        db.delete(Banned_user, Banned_user.user_id == user_id)

    @staticmethod
    def get_banned_users():
        list = db.select(Banned_user)
        return list

    @staticmethod
    def get_banned_user(user_id):
        try:
            return db.select(Banned_user, Banned_user.user_id == user_id)[0]
        except IndexError:
            print(f"IndexError: Banned User {user_id} not found")
            return None


class Reviewer(Base):
    __tablename__ = "reviewers"
    user_id: Mapped[id_pk]
    approve_count: Mapped[int]
    reject_count: Mapped[int]
    approve_but_rejected_count: Mapped[int]
    reject_but_approved_count: Mapped[int]
    last_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"Reviewer(User ID: {self.user_id}, Approve Count: {self.approve_count}, Reject Count: {self.reject_count}, Approve but Rejected Count: {self.approve_but_rejected_count}, Reject but Approved Count: {self.reject_but_approved_count}, Last Date: {self.last_time})"

    @staticmethod
    def count_increase(user_id, column_name, num=1):
        # check reviewer exist or not first
        if not db.select(Reviewer, Reviewer.user_id == user_id):
            db.insert(
                Reviewer,
                user_id=user_id,
                approve_count=0,
                reject_count=0,
                approve_but_rejected_count=0,
                reject_but_approved_count=0,
            )
        current_count = db.select_column(
            Reviewer, column_name, Reviewer.user_id == user_id
        )
        db.update(
            Reviewer,
            Reviewer.user_id == user_id,
            **{column_name: current_count + num},
        )

    @staticmethod
    def get_reviewers():
        return db.select(Reviewer)

    @staticmethod
    def get_reviewer(user_id):
        try:
            return db.select(Reviewer, Reviewer.user_id == user_id)[0]
        except IndexError:
            print(f"IndexError: Reviewer {user_id} not found")
            return None


class DB:
    def __init__(self, database_url):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def select(self, table, condition_expr=True):
        with self.Session.begin() as session:
            stmt = select("*").select_from(table).where(condition_expr)
            result = session.execute(stmt)
            return result.mappings().all()

    def select_column(self, table, column, condition_expr):
        with self.Session.begin() as session:
            stmt = select(getattr(table, column)).where(condition_expr)
            result = session.execute(stmt)
            return result.first()[0]

    def insert(self, table, **kwargs):
        with self.Session.begin() as session:
            new_record = table(**kwargs)
            session.add(new_record)

    def update(self, table, condition_expr, **kwargs):
        with self.Session.begin() as session:
            stmt = update(table).where(condition_expr).values(**kwargs)
            session.execute(stmt)

    def delete(self, table, condition_expr):
        with self.Session.begin() as session:
            stmt = delete(table).where(condition_expr)
            session.execute(stmt)


os.makedirs(Config.DATABASES_DIR, exist_ok=True)
db = DB(f"sqlite:///{Config.DATABASES_DIR / 'system.db'}")
