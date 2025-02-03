import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import MessageOriginType, ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from db_op import Banned_user, Submitter
from env import TG_BANNED_NOTIFY, TG_EXPAND_LENGTH, TG_REVIEWER_GROUP
from review_utils import reply_review_message
from utils import (
    LRUCache,
    send_result_to_submitter,
    send_submission,
)

# set const as the state of one user
COLLECTING = range(1)

# set a dict to store the message from different users, the key is the user_id
message_groups = {}
submission_timestamp = LRUCache(20)


async def confirm_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    user = update.effective_user
    submission = message_groups[user.id]

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

        if len(submission["text"]) > TG_EXPAND_LENGTH:
            submission["text"] = (
                "**>"
                + submission["text"]
                .replace("**>", "")
                .replace("||", "")
                .replace("\n>", "\n")
                .replace("\n", "\n>")
                + "||"
            )

        if query.data.startswith("realname"):
            sign_string = f"_via_ [{escape_markdown(user.full_name,version=2,)}](tg://user?id={user.id})"
            # if the last line is a forward message, put in the same line
            if submission["text"].split("\n")[-1].startswith("_from_"):
                submission["text"] += " " + sign_string
            else:
                submission["text"] += "\n\n" + sign_string

        submission_messages = await send_submission(
            context=context,
            chat_id=TG_REVIEWER_GROUP,
            media_id_list=submission["media_id_list"],
            media_type_list=submission["media_type_list"],
            documents_id_list=submission["document_id_list"],
            document_type_list=submission["document_type_list"],
            text=submission["text"].strip(),
        )
        submission_meta = {
            "submitter": [
                user.id,
                user.username,
                user.full_name,
                submission["first_message_id"],
            ],
            "reviewer": {},
            "text": submission["text"],
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
            submission["first_message_id"],
            "❤️ 投稿成功，阿里嘎多！我们会在稍后通知您审核结果。",
        )

    del message_groups[user.id]
    Submitter.count_increase(user.id, "submission_count")
    return ConversationHandler.END


async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    submission = message_groups[update.effective_user.id]
    message = update.message

    # delete preview messages and last confirm button if they exist
    if submission["last_preview_messages"]:
        for msg in submission["last_preview_messages"]:
            await msg.delete()
    if submission["last_confirm_button"]:
        await submission["last_confirm_button"].delete()
    submission["last_preview_messages"] = []
    submission["last_confirm_button"] = None

    # add new message to this user's message_groups dict
    if message.text_markdown_v2_urled:
        submission["text"] += "\n\n" + message.text_markdown_v2_urled
    if message.caption_markdown_v2_urled:
        submission["text"] += "\n\n" + message.caption_markdown_v2_urled
    if message.photo:
        submission["media_id_list"].append(message.photo[-1].file_id)
        submission["media_type_list"].append("photo")
    if message.video:
        submission["media_id_list"].append(message.video.file_id)
        submission["media_type_list"].append("video")
    if message.sticker:
        submission["media_id_list"].append(message.sticker.file_id)
        submission["media_type_list"].append("sticker")
    if message.animation:  # GIF
        submission["media_id_list"].append(message.animation.file_id)
        submission["media_type_list"].append("animation")
    # elif because gif is also a document but can not be sent as a group
    elif message.document:
        submission["document_id_list"].append(message.document.file_id)
        submission["document_type_list"].append("document")
    if submission["first_message_id"] is None:
        submission["first_message_id"] = message.message_id
    if message.forward_origin is not None:
        forward_string = "\n\n_from_ "
        match message.forward_origin.type:
            case MessageOriginType.USER:
                forward_name = message.forward_origin.sender_user.full_name
                forward_url = (
                    f"tg://user?id={message.forward_origin.sender_user.id}"
                )
                forward_string += f"[{escape_markdown(forward_name,version=2,)}]({forward_url})"
            case MessageOriginType.CHAT:
                forward_name = message.forward_origin.sender_chat.title
                forward_url = message.forward_origin.sender_chat.link
                forward_string += f"[{escape_markdown(forward_name,version=2,)}]({forward_url})"
            case MessageOriginType.CHANNEL:
                forward_name = message.forward_origin.chat.title
                forward_url = f"{message.forward_origin.chat.link}/{message.forward_origin.message_id}"
                forward_string += f"[{escape_markdown(forward_name,version=2,)}]({forward_url})"
            case MessageOriginType.HIDDEN_USER:
                forward_name = message.forward_origin.sender_user_name
                forward_string += escape_markdown(
                    forward_name,
                    version=2,
                )
        if (
            submission["last_origin"] == ""
            or submission["last_origin"] != forward_name
        ):
            submission["text"] += forward_string
        submission["last_origin"] = forward_name
    # show preview of all messages this user has sent
    submission["last_preview_messages"].extend(
        await send_submission(
            context=context,
            chat_id=update.effective_chat.id,
            media_id_list=submission["media_id_list"],
            media_type_list=submission["media_type_list"],
            documents_id_list=submission["document_id_list"],
            document_type_list=submission["document_type_list"],
            text=submission["text"],
        )
    )

    # show options as an inline keyboard
    keyboard = [
        [
            InlineKeyboardButton(
                "署名投稿",
                callback_data=f"realname#{submission["first_message_id"]}",
            ),
            InlineKeyboardButton(
                "匿名投稿",
                callback_data=f"anonymous#{submission["first_message_id"]}",
            ),
        ],
        [InlineKeyboardButton("取消投稿", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    submission["last_confirm_button"] = await message.reply_text(
        "投稿已收到，你可以继续发送消息作为同一组投稿，也可以结束发送，选择匿名投稿、实名投稿或者取消投稿。",
        reply_markup=reply_markup,
    )

    return COLLECTING


async def handle_new_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if Banned_user.is_banned(update.effective_user.id):
        if TG_BANNED_NOTIFY:
            await update.message.reply_text("你已被禁止投稿。")
        return ConversationHandler.END

    await update.message.reply_text(
        "请开始你的投稿，你可以发送多条消息，包括文本和媒体。"
    )
    # empty this user's message_groups dict
    message_groups[update.effective_user.id] = {
        "media_id_list": [],
        "media_type_list": [],
        "document_id_list": [],
        "document_type_list": [],
        "text": "",
        "user_id": update.effective_user.id,
        "user_name": update.effective_user.full_name,
        "last_preview_messages": [],
        "last_confirm_button": None,
        "first_message_id": None,
        "last_origin": "",
    }
    return COLLECTING


async def err_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "错误的命令。\n如果想要重新投稿，请输入 /new"
    )
    return COLLECTING


submission_handler = ConversationHandler(
    entry_points=[CommandHandler("new", handle_new_submission)],
    states={
        COLLECTING: [
            CommandHandler("new", handle_new_submission),
            MessageHandler(filters.ALL & (~filters.COMMAND), collect_data),
            CallbackQueryHandler(confirm_submission),
        ],
    },
    fallbacks=[MessageHandler(filters.COMMAND, err_input)],
)
