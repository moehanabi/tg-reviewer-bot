from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db_op import Banned_user, Submitter
from review_utils import reply_review_message
from utils import TG_BANNED_NOTIFY, TG_REVIEWER_GROUP, send_submission

# set const as the state of one user
COLLECTING = range(1)

# set a dict to store the message from different users, the key is the user_id
message_groups = {}


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
        if query.data.startswith("realname"):
            submission["text"] += f"\n\nby {user.full_name}"
        submission_messages = await send_submission(
            context=context,
            chat_id=TG_REVIEWER_GROUP,
            media_id_list=submission["media_id_list"],
            media_type_list=submission["media_type_list"],
            documents_id_list=submission["document_id_list"],
            document_type_list=submission["document_type_list"],
            text=submission["text"],
        )
        submission_meta = {
            "submitter": [
                user.id,
                user.username,
                user.full_name,
                submission["first_message_id"],
            ],
            "reviewer": {},
            "media_id_list": submission["media_id_list"],
            "media_type_list": submission["media_type_list"],
            "documents_id_list": submission["document_id_list"],
            "document_type_list": submission["document_type_list"],
            "append": {},
        }
        await reply_review_message(submission_messages[0], submission_meta)
        await query.edit_message_text(text="投稿成功")

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
    if message.text:
        submission["text"] += message.text + "\n"
    if message.caption:
        submission["text"] += message.caption + "\n"
    if message.photo:
        submission["media_id_list"].append(message.photo[-1].file_id)
        submission["media_type_list"].append("photo")
    if message.video:
        submission["media_id_list"].append(message.video.file_id)
        submission["media_type_list"].append("video")
    if message.document:
        submission["document_id_list"].append(message.document.file_id)
        submission["document_type_list"].append("document")
    if submission["first_message_id"] is None:
        submission["first_message_id"] = message.message_id

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
            InlineKeyboardButton("实名投稿", callback_data=f"realname"),
            InlineKeyboardButton("匿名投稿", callback_data=f"anonymous"),
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
