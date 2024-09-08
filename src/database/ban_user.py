from sqlalchemy import delete, select

from src.database import Banned_user, SessionFactory


async def is_banned(user_id: int) -> Banned_user | None:
    """
    Check if a user is banned based on their user ID.
    Args:
        user_id (int): The ID of the user to check.
    Returns:
        Banned_user: The Banned_user object if the user is banned, otherwise None.
    """
    async with SessionFactory as session:
        user_data = await session.execute(select(Banned_user).filter_by(user_id=user_id))
        return user_data.scalar_one_or_none()


async def unban_user(user_id: int) -> bool:
    """
    Unban a user based on their user ID.
    Args:
        user_id (int): The ID of the user to unban.
    Returns:
        bool: True if the user was successfully unbanned, otherwise False
    """
    async with SessionFactory as session:
        ret = await session.execute(delete(Banned_user).filter_by(user_id=user_id))
        return ret.rowcount > 0


async def get_all_banned_users() -> list[Banned_user]:
    """
    Retrieve all banned users.
    Returns:
        list[Banned_user]: A list of all banned users.
    """
    async with SessionFactory as session:
        ban_list = await session.execute(select(Banned_user))
        return ban_list.scalars().all()


async def get_banned_user(user_id: int) -> Banned_user | None:
    async with SessionFactory as session:
        ret = await session.execute(select(Banned_user).filter_by(user_id=user_id))
        return ret.scalar_one_or_none()
