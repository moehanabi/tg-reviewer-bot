import logging
from telegram.ext import ApplicationBuilder
from submit import submission_handler
from utils import TG_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TG_TOKEN).build()

    application.add_handler(submission_handler)
    application.run_polling()
