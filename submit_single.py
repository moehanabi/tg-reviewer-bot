import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import MessageOriginType, ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from db_op import Submitter
from env import TG_EXPAND_LENGTH, TG_REVIEWER_GROUP, TG_REVIEWONLY
from review_utils import reply_review_message
from utils import (
    LRUCache,
    check_submission,
    send_result_to_submitter,
    send_submission,
)

media_groups = {}
submission_timestamp = LRUCache(20)


async def reply_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_submission(update) == False:
        return

    if TG_REVIEWONLY:
        await update.message.reply_text(
            "本 Bot 已暂停使用。请查看频道获取更多信息",
            quote=True,)
        return

    message = update.message

    if message.media_group_id:
        if message.media_group_id in media_groups:
            submission = media_groups[message.media_group_id]
        else:
            submission = {
                "media_id_list": [],
                "media_type_list": [],
                "document_id_list": [],
                "document_type_list": [],
            }
        if message.photo:
            submission["media_id_list"].append(message.photo[-1].file_id)
            submission["media_type_list"].append("photo")
        if message.video:
            submission["media_id_list"].append(message.video.file_id)
            submission["media_type_list"].append("video")
        if message.animation:  # GIF
            submission["media_id_list"].append(message.animation.file_id)
            submission["media_type_list"].append("animation")
        # elif because gif is also a document but can not be sent as a group
        elif message.document:
            submission["document_id_list"].append(message.document.file_id)
            submission["document_type_list"].append("document")

        if message.media_group_id in media_groups:
            return
        media_groups[message.media_group_id] = submission

    # show options as an inline keyboard
    keyboard = [
        [
            InlineKeyboardButton(
                "署名投稿", callback_data=f"realname#{message.message_id}"
            ),
            InlineKeyboardButton(
                "匿名投稿", callback_data=f"anonymous#{message.message_id}"
            ),
        ],
        [InlineKeyboardButton("取消投稿", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        """❔确认投稿？（确认后无法编辑内容）

请确认稿件不包含以下内容，否则可能不会被通过：
- 过于哗众取宠、摆拍卖蠢（傻逼不算沙雕）
- 火星救援
- 纯链接（请投稿链接里的内容，如图片、视频等）
- 恶俗性挂人

稿件将由多位管理投票审核，每位管理的审核标准可能不一，投票制可以改善这类问题，但仍可能对部分圈内的梗不太熟悉，请您理解""",
        quote=True,
        reply_markup=reply_markup,
    )


async def confirm_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    user = update.effective_user

    confirm_message = update.effective_message
    origin_message = confirm_message.reply_to_message

    if query.data.startswith("cancel"):
        await query.edit_message_text(text="投稿已取消")
    elif query.data.startswith(("anonymous", "realname")):
        submission_id = int(query.data.split("#")[-1])
        last_submission_time = submission_timestamp.get(submission_id)
        if (
            last_submission_time != -1
            and int(time.time()) - last_submission_time < 10
        ):
            try:
                await query.edit_message_text(
                    text="请勿重复点按。\n若 10 秒后没有变化请再考虑重新投递。",
                    reply_markup=query.message.reply_markup,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
            except:
                return
        else:
            submission_timestamp.put(submission_id, int(time.time()))

        text = (
            origin_message.text_markdown_v2_urled
            or origin_message.caption_markdown_v2_urled
            or ""
        )
        if len(text) > TG_EXPAND_LENGTH:
            text = (
                "**>"
                + text.replace("**>", "")
                .replace("||", "")
                .replace("\n>", "\n")
                .replace("\n", "\n>")
                + "||"
            )
        # add forward origin
        if origin_message.forward_origin is not None:
            forward_string = "\n\n_from_ "
            match origin_message.forward_origin.type:
                case MessageOriginType.USER:
                    forward_string += f"[{escape_markdown(origin_message.forward_origin.sender_user.full_name,version=2,)}](tg://user?id={origin_message.forward_origin.sender_user.id})"
                case MessageOriginType.CHAT:
                    forward_string += f"[{escape_markdown(origin_message.forward_origin.sender_chat.title,version=2,)}]({origin_message.forward_origin.sender_chat.link})"
                case MessageOriginType.CHANNEL:
                    forward_string += f"[{escape_markdown(origin_message.forward_origin.chat.title,version=2,)}]({origin_message.forward_origin.chat.link}/{origin_message.forward_origin.message_id})"
                case MessageOriginType.HIDDEN_USER:

                    forward_string += escape_markdown(
                        origin_message.forward_origin.sender_user_name,
                        version=2,
                    )
            text += f"{forward_string}"

        # add submitter sign string
        if query.data.startswith("realname"):
            sign_string = f"_via_ [{escape_markdown(user.full_name,version=2,)}](tg://user?id={user.id})"
            # if the last line is a forward message, put in the same line
            if text.split("\n")[-1].startswith("_from_"):
                text += " " + sign_string
            else:
                text += "\n\n" + sign_string

        if origin_message.media_group_id:
            # is a group of media
            submission = media_groups[origin_message.media_group_id]
            pass
        else:
            # single media or pure text
            submission = {
                "media_id_list": [],
                "media_type_list": [],
                "document_id_list": [],
                "document_type_list": [],
            }
            if origin_message.photo:
                submission["media_id_list"].append(
                    origin_message.photo[-1].file_id
                )
                submission["media_type_list"].append("photo")
            if origin_message.video:
                submission["media_id_list"].append(
                    origin_message.video.file_id
                )
                submission["media_type_list"].append("video")
            if origin_message.sticker:
                submission["media_id_list"].append(
                    origin_message.sticker.file_id
                )
                submission["media_type_list"].append("sticker")
                # just ignore any forward or realname infomation for sticker
                # in single submit mode because it is not allowed to have
                # text with sticker
                text = ""
            if origin_message.animation:  # GIF
                submission["media_id_list"].append(
                    origin_message.animation.file_id
                )
                submission["media_type_list"].append("animation")
            # elif because gif is also a document but can not be sent as a group
            elif origin_message.document:
                submission["document_id_list"].append(
                    origin_message.document.file_id
                )
                submission["document_type_list"].append("document")

        submission_messages = await send_submission(
            context=context,
            chat_id=TG_REVIEWER_GROUP,
            media_id_list=submission["media_id_list"],
            media_type_list=submission["media_type_list"],
            documents_id_list=submission["document_id_list"],
            document_type_list=submission["document_type_list"],
            text=text.strip(),
        )

        submission_meta = {
            "submitter": [
                user.id,
                user.username,
                user.full_name,
                origin_message.message_id,
            ],
            "reviewer": {},
            "text": text,
            "media_id_list": submission["media_id_list"],
            "media_type_list": submission["media_type_list"],
            "documents_id_list": submission["document_id_list"],
            "document_type_list": submission["document_type_list"],
            "append": {},
        }

        await reply_review_message(
            submission_messages[0], submission_meta, context
        )
        await query.delete_message()
        await send_result_to_submitter(
            context,
            user.id,
            origin_message.message_id,
            "❤️ 投稿成功，阿里嘎多！我们会在稍后通知您审核结果。",
        )

        Submitter.count_increase(user.id, "submission_count")


submission_handler = MessageHandler(
    filters.ChatType.PRIVATE & ~filters.COMMAND, reply_option
)
confirm_submit_handler = CallbackQueryHandler(
    confirm_submission,
    pattern="^(cancel|anonymous|realname)",
)
