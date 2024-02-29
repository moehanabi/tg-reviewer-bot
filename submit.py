from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, ConversationHandler, filters
from utils import TG_REVIEWER_GROUP

# set const as the state of one user
COLLECTING = range(1)

# set a dict to store the message from different users, the key is the user_id
message_groups = {}


async def confirm_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    submission = message_groups[update.effective_user.id]

    if query.data.startswith("cancel"):
        await query.edit_message_text(text="投稿已取消")
    elif query.data.startswith("anonymous"):
        message_id = query.data.split(".")[1]
        await send_media(
            context=context,
            chat_id=TG_REVIEWER_GROUP,
            media=submission['media'],
            documents=submission['documents'],
            text=submission['text']
        )

        await query.edit_message_text(text="投稿成功")
    elif query.data.startswith("realname"):
        message_id = query.data.split(".")[1]
        await send_media(
            context=context,
            chat_id=TG_REVIEWER_GROUP,
            media=submission['media'],
            documents=submission['documents'],
            text=f"{submission['text']}\n\nby {update.effective_user.full_name}"
        )

        await query.edit_message_text(text="投稿成功")

    del message_groups[update.effective_user.id]
    return ConversationHandler.END


async def send_group(context: ContextTypes.DEFAULT_TYPE, chat_id, media=[], text=""):
    for i in range(0, len(media), 10):
        portion = media[i:i+10]
        if len(portion) == 1:
            if type(portion[0]) == InputMediaPhoto:
                await context.bot.send_photo(chat_id=chat_id, photo=portion[0].media, caption=text)
            elif type(portion[0]) == InputMediaVideo:
                await context.bot.send_video(chat_id=chat_id, video=portion[0].media, caption=text)
        else:
            await context.bot.send_media_group(chat_id=chat_id, media=portion, caption=text)


async def send_media(context: ContextTypes.DEFAULT_TYPE, chat_id, media=[], documents=[], text=""):
    if len(media) == 0 and len(documents) == 0:
        await context.bot.send_message(chat_id=chat_id, text=text)
        return
    if len(media) > 0:
        await send_group(context=context, chat_id=chat_id, media=media, text=text)
    if len(documents) > 0:
        await send_group(context=context, chat_id=chat_id, media=documents, text=text)


async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    submission = message_groups[update.effective_user.id]
    message = update.message
    # add new message to this user's message_groups dict
    submission['messages'].append(message)
    # show preview of all messages this user has sent
    if message.text:
        submission['text'] += message.text + "\n"
    if message.caption:
        submission['text'] += message.caption + "\n"
    if message.photo:
        submission['media'].append(InputMediaPhoto(message.photo[-1]))
    if message.video:
        submission['media'].append(InputMediaVideo(message.video))
    if message.document:
        submission['documents'].append(InputMediaDocument(message.document))

    await send_media(context=context, chat_id=update.effective_chat.id, media=submission['media'], documents=submission['documents'], text=submission['text'])

    # show options as an inline keyboard
    keyboard = [
        [
            # we should carry on the message_id as the callback_data
            # because in confirm_submission we can not get the message_id anymore
            InlineKeyboardButton(
                "匿名投稿", callback_data=f"anonymous.{update.message.message_id}"),
            InlineKeyboardButton(
                "实名投稿", callback_data=f"realname.{update.message.message_id}"),
        ],
        [
            InlineKeyboardButton("取消投稿", callback_data="cancel")
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("投稿已收到，你可以继续发送消息作为同一组投稿，也可以结束发送，选择匿名投稿、实名投稿或者取消投稿。", reply_markup=reply_markup)

    return COLLECTING


async def handle_new_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("请开始你的投稿，你可以发送多条消息，包括文本和媒体。")
    # empty this user's message_groups dict
    message_groups[update.effective_user.id] = {
        'messages': [],
        'media': [],
        'documents': [],
        'text': '',
        'user_id': update.effective_user.id,
        'user_name': update.effective_user.full_name
    }
    return COLLECTING


async def err_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("错误的命令。\n如果想要重新投稿，请输入 /new")
    return COLLECTING

submission_handler = ConversationHandler(
    entry_points=[CommandHandler("new", handle_new_submission)],
    states={
        COLLECTING: [
            CommandHandler("new", handle_new_submission),
            MessageHandler(filters.ALL & (~filters.COMMAND), collect_data),
            CallbackQueryHandler(confirm_submission)
        ],
    },
    fallbacks=[MessageHandler(filters.COMMAND, err_input)],
)
