import asyncio
import logging

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.ban import ban_user, list_banned_users, unban_user
from src.config import Config, ReviewConfig
from src.review import (
    approve_submission,
    query_decision,
    reject_submission,
    withdraw_decision,
)
from src.review_utils import (
    ReviewChoice,
    append_message,
    comment_message,
    reject_reason,
    remove_append_message,
    retract_approved_submission,
    send_custom_rejection_reason,
)
from src.stats import reviewer_stats, submitter_stats
from src.utils import PrefixFilter, get_username

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=Config.LOG_LEVE,
)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    BOT_USERNAME = loop.run_until_complete(get_username())
    application = (
        ApplicationBuilder()
        .token(Config.BOT_TOKEN)
        .get_updates_connect_timeout(60)
        .connect_timeout(60)
        .get_updates_read_timeout(60)
        .read_timeout(60)
        .get_updates_write_timeout(60)
        .write_timeout(60)
        .build()
    )

    if ReviewConfig.SINGLE_MODE:
        from src.submit_single import confirm_submit_handler, submission_handler

        application.add_handler(confirm_submit_handler)
    else:
        from src.submit import submission_handler

    application.add_handler(submission_handler)
    application.add_handlers(
        [
            CallbackQueryHandler(
                approve_submission,
                pattern=f"^({ReviewChoice.SFW}|{ReviewChoice.NSFW})",
            ),
            CallbackQueryHandler(
                reject_submission,
                pattern=f"^({ReviewChoice.REJECT}|{ReviewChoice.REJECT_DUPLICATE})",
            ),
            CallbackQueryHandler(query_decision, pattern=f"^{ReviewChoice.QUERY}"),
            CallbackQueryHandler(
                withdraw_decision, pattern=f"^{ReviewChoice.WITHDRAW}"
            ),
            CallbackQueryHandler(
                retract_approved_submission,
                pattern=f"^{ReviewChoice.APPROVED_RETRACT}",
            ),
            CallbackQueryHandler(reject_reason, pattern=f"^REASON"),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP))
                & (
                    PrefixFilter("/append ") | PrefixFilter(f"@{BOT_USERNAME} /append ")
                ),
                append_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP))
                & (
                    PrefixFilter("/remove_append ")
                    | PrefixFilter(f"@{BOT_USERNAME} /remove_append ")
                ),
                remove_append_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP))
                & (
                    PrefixFilter("/comment ")
                    | PrefixFilter(f"@{BOT_USERNAME} /comment ")
                ),
                comment_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP))
                & (
                    PrefixFilter("/reject ") | PrefixFilter(f"@{BOT_USERNAME} /reject ")
                ),
                send_custom_rejection_reason,
            ),
            CommandHandler(
                "ban",
                ban_user,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP)),
            ),
            CommandHandler(
                "unban",
                unban_user,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP)),
            ),
            CommandHandler(
                "listban",
                list_banned_users,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP)),
            ),
            CommandHandler(
                "stats",
                submitter_stats,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            ),
            CommandHandler(
                "reviewer_stats",
                reviewer_stats,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(ReviewConfig.REVIEWER_GROUP)),
            ),
        ]
    )
    application.run_polling()
