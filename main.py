import logging
from telegram.ext import ApplicationBuilder, CallbackQueryHandler
from submit import submission_handler
from utils import TG_TOKEN
from review import approve_submission, reject_submission, query_decision, withdraw_decision, ReviewChoice, reject_reason

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TG_TOKEN).get_updates_connect_timeout(60).connect_timeout(
        60).get_updates_read_timeout(60).read_timeout(60).get_updates_write_timeout(60).write_timeout(60).build()

    application.add_handler(submission_handler)

    application.add_handlers([
        CallbackQueryHandler(approve_submission, pattern=f"^({ReviewChoice.SFW}|{ReviewChoice.NSFW})"),
        CallbackQueryHandler(
            reject_submission, pattern=f"^({ReviewChoice.REJECT}|{ReviewChoice.REJECT_DUPLICATE})"),
        CallbackQueryHandler(query_decision, pattern=f"^{ReviewChoice.QUERY}"),
        CallbackQueryHandler(withdraw_decision, pattern=f"^{ReviewChoice.WITHDRAW}"),
        CallbackQueryHandler(reject_reason, pattern=f"^REASON")
    ])
    application.run_polling()
