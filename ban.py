from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from db_op import Banned_origin, Banned_user
from utils import get_name_from_uid, is_integer


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
    if Banned_user.is_banned(user):
        await update.message.reply_text(
            f"{user} 先前已被屏蔽\n"
            + await get_banned_user_info(
                context, Banned_user.get_banned_user(user)
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    username, fullname = await get_name_from_uid(context, user)
    Banned_user.ban_user(
        user, username, fullname, update.effective_user.id, " ".join(result)
    )
    if Banned_user.is_banned(user):
        await update.message.reply_text(
            await get_banned_user_info(
                context, Banned_user.get_banned_user(user)
            )
            + escape_markdown(
                f"\n\n#BAN_{user} #OPERATOR_{update.effective_user.id}",
                version=2,
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{user}* 屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def get_banned_user_info(context: ContextTypes.DEFAULT_TYPE, user):
    banned_userinfo = escape_markdown(
        f"{user.user_fullname} ({f'@{user.user_name}, ' if user.user_name else ''}{user.user_id})",
        version=2,
    )
    banned_by_username, banned_by_fullname = await get_name_from_uid(
        context, user.banned_by
    )
    banned_by_userinfo = escape_markdown(
        f"{banned_by_fullname} ({banned_by_username}, {user.banned_by})",
        version=2,
    )
    users_string = f"*{banned_userinfo}* 在 *{escape_markdown(str(user['banned_date']), version=2)}* 由 *{banned_by_userinfo}* 因 *{escape_markdown(user['banned_reason'], version=2)}* 屏蔽"
    return users_string


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
            f"*{user}* "
            + escape_markdown(
                f"已解除屏蔽\n\n#UNBAN_{user} #OPERATOR_{update.effective_user.id}",
                version=2,
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def list_banned_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    users = Banned_user.get_banned_users()
    list_banned_users_page_count = 1
    users_string = ("屏蔽用户列表:\n页面" + str(list_banned_users_page_count) + "\n") if users else "无屏蔽用户\n"
    for user in users:
        new_banned_usr_str = f"\- {await get_banned_user_info(context, user)}\n"
        if len(users_string + new_banned_usr_str) >= 1300:
            user_string += "（未完待续）"
            await update.message.reply_text(
                users_string,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            list_banned_users_page_count += 1
            users_string = "屏蔽用户列表:\n页面" + str(list_banned_users_page_count) + "\n"
        users_string += new_banned_usr_str
    await update.message.reply_text(
        users_string,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def ban_origin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供来源频道或用户 ID 和原因",
        )
        return
    origin, result = context.args[0], context.args[1:]
    if not is_integer(origin):
        await update.message.reply_text(
            f"ID *{escape_markdown(origin,version=2,)}* 无效",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    if Banned_origin.is_banned(origin):
        await update.message.reply_text(
            f"{origin} 先前已被屏蔽\n"
            + await get_banned_origin_info(
                context, Banned_origin.get_banned_origin(origin)
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    Banned_origin.ban_origin(
        origin, update.effective_user.id, " ".join(result)
    )
    if Banned_origin.is_banned(origin):
        await update.message.reply_text(
            await get_banned_origin_info(
                context, Banned_origin.get_banned_origin(origin)
            )
            + escape_markdown(
                f"\n\n#BAN_ORIGIN_{origin.replace("-", "")} #OPERATOR_{update.effective_user.id}",
                version=2,
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{origin}* 屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def get_banned_origin_info(context: ContextTypes.DEFAULT_TYPE, origin):
    banned_origininfo = escape_markdown(
        f"({origin.origin_id})",
        version=2,
    )
    banned_by_originname, banned_by_fullname = await get_name_from_uid(
        context, origin.banned_by
    )
    banned_by_origininfo = escape_markdown(
        f"{banned_by_fullname} ({banned_by_originname}, {origin.banned_by})",
        version=2,
    )
    origins_string = f"*{banned_origininfo}* 在 *{escape_markdown(str(origin['banned_date']), version=2)}* 由 *{banned_by_origininfo}* 因 *{escape_markdown(origin['banned_reason'], version=2)}* 屏蔽"
    return origins_string


async def unban_origin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供来源频道或用户 ID",
        )
        return
    origin = context.args[0]

    Banned_origin.unban_origin(origin)
    if Banned_origin.is_banned(origin):
        await update.message.reply_text(
            f"*{origin}* 解除屏蔽失败",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text(
            f"*{escape_markdown(origin, version=2,)}* "
            + escape_markdown(
                f"已解除屏蔽\n\n#UNBAN_ORIGIN_{origin.replace("-", "")} #OPERATOR_{update.effective_user.id}",
                version=2,
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def list_banned_origins(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    origins = Banned_origin.get_banned_origins()
    origins_string = "屏蔽来源列表:\n" if origins else "无屏蔽来源\n"
    for origin in origins:
        origins_string += (
            f"\- {await get_banned_origin_info(context, origin)}\n"
        )
    await update.message.reply_text(
        origins_string,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
