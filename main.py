import logging
from telegram.ext import ApplicationBuilder
from submit import submission_handler
from utils import TG_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TG_TOKEN).get_updates_connect_timeout(60).connect_timeout(
        60).get_updates_read_timeout(60).read_timeout(60).get_updates_write_timeout(60).write_timeout(60).build()

    application.add_handler(submission_handler)
    application.run_polling()
