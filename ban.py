from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from db_op import Banned_user


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.text.split("/ban ")[1]
    Banned_user.ban_user(user, update.effective_user.id)
    if Banned_user.is_banned(user):
        user = Banned_user.get_banned_user(user)
        await update.message.reply_text(
            f"*{user.user_id}* 在 *{escape_markdown(str(user.banned_date), version=2)}* 由 *{user.banned_by}* 屏蔽",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{user}* 屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.text.split("/unban ")[1]
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
        users_string += f"\- *{user.user_id}* 在 *{escape_markdown(str(user.banned_date), version=2)}* 由 *{user.banned_by}* 屏蔽\n"
    await update.message.reply_text(
        users_string,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
