from typing import Optional

from sqlalchemy import select

from src.database import SessionFactory, SubmitterModel


async def count_modify(user_id: int, column_name: str, num: Optional[int] = 1) -> SubmitterModel:
    """
    修改统计数据
    Args:
        user_id (int): The ID of the user whose count is to be modified.
        column_name (str): The name of the column to be modified.
        num (Optional[int], optional): The number to modify the count by. Defaults to 1.
    Returns:
        SubmitterModel: The updated Submitter object.
    """
    async with SessionFactory() as session:
        async with session.begin():
            user_data = await session.execute(select(SubmitterModel).filter_by(user_id=user_id))
            if not (user_data := user_data.scalar_one_or_none()):
                user_data = SubmitterModel(user_id=user_id, submission_count=0, approved_count=0, rejected_count=0, )
            setattr(user_data, column_name, getattr(user_data, column_name, 0) + num)
            session.merge(user_data)
        return user_data


async def get_submitter(user_id: int) -> SubmitterModel | None:
    """
    Retrieve a submitter by user ID.
    Args:
        user_id (int): The ID of the user to retrieve.
    Returns:
        SubmitterModel: The retrieved Submitter object.
    """
    async with SessionFactory() as session:
        user_data = await session.execute(select(SubmitterModel).filter_by(user_id=user_id))
        return user_data.scalar_one_or_none()
