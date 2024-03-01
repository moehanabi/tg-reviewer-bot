import os
from telegram import InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes

# get args from environment virables
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_REVIEWER_GROUP = os.environ.get('TG_REVIEWER_GROUP')
TG_PUBLISH_CHANNEL = os.environ.get('TG_PUBLISH_CHANNEL')


async def send_group(context: ContextTypes.DEFAULT_TYPE, chat_id, media=[], text=""):
    sent_messages = []

    for i in range(0, len(media), 10):
        portion = media[i:i+10]
        if len(portion) == 1:
            if type(portion[0]) == InputMediaPhoto:
                sent_messages.append(await context.bot.send_photo(chat_id=chat_id, photo=portion[0].media, caption=text))
            elif type(portion[0]) == InputMediaVideo:
                sent_messages.append(await context.bot.send_video(chat_id=chat_id, video=portion[0].media, caption=text))
        else:
            sent_messages.extend(await context.bot.send_media_group(chat_id=chat_id, media=portion, caption=text))

    return sent_messages


async def send_submission(context: ContextTypes.DEFAULT_TYPE, chat_id, media=None, documents=None, text=""):
    sent_messages = []

    media_list = media if media else []
    documents_list = documents if documents else []

    # no media or documents, just send text
    if not media_list and not documents_list:
        sent_messages.append(await context.bot.send_message(chat_id=chat_id, text=text))
        return sent_messages

    # send media and documents
    for m_list in [media_list, documents_list]:
        if m_list:
            sent_messages.extend(await send_group(context=context, chat_id=chat_id, media=m_list, text=text))

    return sent_messages
