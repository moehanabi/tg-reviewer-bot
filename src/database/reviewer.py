from typing import Optional

from sqlalchemy import select

from src.database import ReviewerModel, SessionFactory


async def count_modify(user_id: int, column_name: str, num: Optional[int] = 1) -> ReviewerModel:
    """
    修改统计数据
     Args:
        user_id (int): The ID of the user whose count is to be modified.
        column_name (str): The name of the column to be modified.
        num (Optional[int], optional): The number to modify the count by. Defaults to 1.
    Returns:
        ReviewerModel: The updated ReviewerModel object.
    """
    async with SessionFactory() as session:
        async with session.begin():
            user_data = await session.execute(select(ReviewerModel).filter_by(user_id=user_id))
            if not (user_data := user_data.scalar_one_or_none()):
                user_data = ReviewerModel(user_id=user_id, approve_count=0, reject_count=0, approve_but_rejected_count=0,
                                          reject_but_approved_count=0, )
            setattr(user_data, column_name, getattr(user_data, column_name, 0) + num)
            session.merge(user_data)
        return user_data


async def get_reviewer(user_id: int) -> ReviewerModel | None:
    """
    Retrieve a reviewer by user ID.
    Args:
        user_id (int): The ID of the user to retrieve.
    Returns:
        ReviewerModel: The retrieved Reviewer object.
    """
    async with SessionFactory() as session:
        user_data = await session.execute(select(ReviewerModel).filter_by(user_id=user_id))
        return user_data.scalar_one_or_none()
