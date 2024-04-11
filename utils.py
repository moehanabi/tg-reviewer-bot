import os

from telegram import (
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    ReplyParameters,
)
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

# get args from environment virables
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_REVIEWER_GROUP = os.environ.get("TG_REVIEWER_GROUP")
TG_PUBLISH_CHANNEL = os.environ.get("TG_PUBLISH_CHANNEL")
TG_REJECTED_CHANNEL = os.environ.get("TG_REJECTED_CHANNEL")
TG_BOT_USERNAME = os.environ.get("TG_BOT_USERNAME")
TG_RETRACT_NOTIFY = os.getenv("TG_RETRACT_NOTIFY", "True") == "True"
try:
    APPROVE_NUMBER_REQUIRED = int(os.getenv("TG_APPROVE_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    APPROVE_NUMBER_REQUIRED = 2
try:
    REJECT_NUMBER_REQUIRED = int(os.getenv("TG_REJECT_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    REJECT_NUMBER_REQUIRED = 2
REJECTION_REASON = os.environ.get("TG_REJECTION_REASON", "").split(":")


class PrefixFilter(MessageFilter):
    prefix = "/append"

    def __init__(self, prefix):
        super().__init__()
        self.prefix = prefix

    def filter(self, message):
        return message.text.startswith(self.prefix)


async def send_group(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id,
    item_list,
    type_list,
    text="",
    has_spoiler=False,
):
    sent_messages = []

    # use item_list and type_list to build a list of telegram.InputMediaDocument, telegram.InputMediaPhoto, telegram.InputMediaVideo
    media = []
    for i in range(len(item_list)):
        match type_list[i]:
            case "photo":
                media.append(
                    InputMediaPhoto(item_list[i], has_spoiler=has_spoiler)
                )
            case "video":
                media.append(
                    InputMediaVideo(item_list[i], has_spoiler=has_spoiler)
                )
            case "document":
                media.append(InputMediaDocument(item_list[i]))

    for i in range(0, len(media), 10):
        portion = media[i : i + 10]
        if len(portion) > 1:
            sent_messages.extend(
                await context.bot.send_media_group(
                    chat_id=chat_id, media=portion, caption=text
                )
            )
            continue
        match portion[0]:
            case InputMediaPhoto():
                sent_messages.append(
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=portion[0].media,
                        caption=text,
                        has_spoiler=has_spoiler,
                    )
                )
            case InputMediaVideo():
                sent_messages.append(
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=portion[0].media,
                        caption=text,
                        has_spoiler=has_spoiler,
                    )
                )
            case InputMediaDocument():
                sent_messages.append(
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=portion[0].media,
                        caption=text,
                    )
                )

    return sent_messages


async def send_submission(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id,
    media_id_list,
    media_type_list,
    documents_id_list,
    document_type_list,
    text="",
    has_spoiler=False,
):
    sent_messages = []

    # no media or documents, just send text
    if not media_id_list and not documents_id_list:
        sent_messages.append(
            await context.bot.send_message(chat_id=chat_id, text=text)
        )
        return sent_messages

    # send media and documents
    if media_id_list:
        sent_messages.extend(
            await send_group(
                context=context,
                chat_id=chat_id,
                item_list=media_id_list,
                type_list=media_type_list,
                text=text,
                has_spoiler=has_spoiler,
            )
        )
    if documents_id_list:
        sent_messages.extend(
            await send_group(
                context=context,
                chat_id=chat_id,
                item_list=documents_id_list,
                type_list=document_type_list,
                text=text,
            )
        )

    return sent_messages


async def send_result_to_submitter(
    context,
    submitter_id,
    submit_message_id,
    message,
    inline_keyboard_markup=None,
):
    try:
        await context.bot.send_message(
            chat_id=submitter_id,
            text=message,
            reply_parameters=ReplyParameters(
                submit_message_id, allow_sending_without_reply=True
            ),
            reply_markup=inline_keyboard_markup,
        )
    except:
        pass
