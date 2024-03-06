import os
from telegram import InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes

# get args from environment virables
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_REVIEWER_GROUP = os.environ.get('TG_REVIEWER_GROUP')
TG_PUBLISH_CHANNEL = os.environ.get('TG_PUBLISH_CHANNEL')
APPROVE_NUMBER_REQUIRED = 2
REJECT_NUMBER_REQUIRED = 2
REJECTION_REASON = os.environ.get('TG_REJECTION_REASON').split(":")


async def send_group(context: ContextTypes.DEFAULT_TYPE, chat_id, item_list, type_list, text=""):
    sent_messages = []

    # use item_list and type_list to build a list of telegram.InputMediaDocument, telegram.InputMediaPhoto, telegram.InputMediaVideo
    media = []
    for i in range(len(item_list)):
        match type_list[i]:
            case "photo":
                media.append(InputMediaPhoto(item_list[i]))
            case "video":
                media.append(InputMediaVideo(item_list[i]))
            case "document":
                media.append(InputMediaDocument(item_list[i]))

    for i in range(0, len(media), 10):
        portion = media[i:i+10]
        if len(portion) > 1:
            sent_messages.extend(await context.bot.send_media_group(chat_id=chat_id, media=portion, caption=text))
            continue
        match type(portion[0]):
            case "InputMediaPhoto":
                sent_messages.append(await context.bot.send_photo(chat_id=chat_id, photo=portion[0].file_id, caption=text))
            case "InputMediaVideo":
                sent_messages.append(await context.bot.send_video(chat_id=chat_id, video=portion[0].file_id, caption=text))
            case "InputMediaDocument":
                sent_messages.append(await context.bot.send_document(chat_id=chat_id, document=portion[0].file_id, caption=text))

    return sent_messages


async def send_submission(context: ContextTypes.DEFAULT_TYPE, chat_id, media_id_list, media_type_list, documents_id_list, document_type_list, text=""):
    sent_messages = []

    # no media or documents, just send text
    if not media_id_list and not documents_id_list:
        sent_messages.append(await context.bot.send_message(chat_id=chat_id, text=text))
        return sent_messages

    # send media and documents
    if media_id_list:
        sent_messages.extend(await send_group(context=context, chat_id=chat_id, item_list=media_id_list, type_list=media_type_list, text=text))
    if documents_id_list:
        sent_messages.extend(await send_group(context=context, chat_id=chat_id, item_list=documents_id_list, type_list=document_type_list, text=text))

    return sent_messages
