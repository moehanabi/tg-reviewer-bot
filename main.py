import logging
from telegram.ext import ApplicationBuilder, CommandHandler
from submit import *
from utils import TG_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TG_TOKEN).build()

    new_submission_handler = CommandHandler('new', handle_new_sumission)
    application.add_handler(new_submission_handler)

    application.run_polling()
