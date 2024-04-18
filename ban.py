from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from db_op import Banned_user
from utils import get_name_from_uid


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供用户ID和原因",
        )
        return
    user, result = context.args[0], context.args[1:]
    if not user.isdigit():
        await update.message.reply_text(
            f"ID *{escape_markdown(user,version=2,)}* 无效",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    username, fullname = await get_name_from_uid(context, user)
    Banned_user.ban_user(
        user, username, fullname, update.effective_user.id, " ".join(result)
    )
    if Banned_user.is_banned(user):
        banned_user = Banned_user.get_banned_user(user)
        banned_userinfo = escape_markdown(
            f"{fullname} ({f'@{username}, ' if username else ''}{user})",
            version=2,
        )
        banned_by_userinfo = escape_markdown(
            f"{update.effective_user.full_name} (@{update.effective_user.username}, {update.effective_user.id})",
            version=2,
        )
        await update.message.reply_text(
            f"*{banned_userinfo}* 在 *{escape_markdown(str(banned_user['banned_date']), version=2)}* 由 *{banned_by_userinfo}* 因 *{banned_user['banned_reason']}* 屏蔽",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{user}* 屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供用户ID",
        )
        return
    user = context.args[0]
    Banned_user.unban_user(user)
    if Banned_user.is_banned(user):
        await update.message.reply_text(
            f"*{user}* 解除屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{user}* 已解除屏蔽",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def list_banned_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    users = Banned_user.get_banned_users()
    users_string = "屏蔽用户列表:\n" if users else "无屏蔽用户\n"
    for user in users:
        banned_userinfo = escape_markdown(
            f"{user.user_fullname} ({f'@{user.user_name}, ' if user.user_name else ''}{user.user_id})",
            version=2,
        )
        banned_by_username, banned_by_fullname = await get_name_from_uid(
            context, user.banned_by
        )
        banned_by_userinfo = escape_markdown(
            f"{banned_by_fullname} (@{banned_by_username}, {user.banned_by})",
            version=2,
        )
        users_string += f"\- *{banned_userinfo}* 在 *{escape_markdown(str(user['banned_date']), version=2)}* 由 *{banned_by_userinfo}* 因 *{user['banned_reason']}* 屏蔽\n"
    await update.message.reply_text(
        users_string,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
