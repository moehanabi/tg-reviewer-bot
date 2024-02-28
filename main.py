import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler
from submit import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    # get args from environment virables
    TG_TOKEN = os.environ.get('TG_TOKEN')
    TG_REVIEWER_GROUP = os.environ.get('TG_REVIEWER_GROUP')
    TG_PUBLISH_CHANNEL = os.environ.get('TG_PUBLISH_CHANNEL')

    application = ApplicationBuilder().token(TG_TOKEN).build()

    new_submission_handler = CommandHandler('new', handle_new_sumission)
    application.add_handler(new_submission_handler)

    application.run_polling()
