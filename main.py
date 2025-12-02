import logging

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from ban import (
    ban_origin,
    ban_user,
    list_banned_origins,
    list_banned_users,
    unban_origin,
    unban_user,
)
from env import TG_BOT_USERNAME, TG_REVIEWER_GROUP, TG_SINGLE_MODE, TG_TOKEN, TG_CUSTOMAPI
from review import (
    approve_submission,
    query_decision,
    reject_submission,
    withdraw_decision,
)
from review_utils import (
    ReviewChoice,
    append_message,
    comment_message,
    reject_reason,
    remove_append_message,
    retract_approved_submission,
    send_custom_rejection_reason,
)
from stats import (
    get_set_default_max_submission_per_hour,
    get_set_submitter_max_submission_per_hour,
    reset_submitter_max_submission_per_hour,
    reviewer_stats,
    submitter_stats,
)
from utils import PrefixFilter

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token(TG_TOKEN)
        .base_url(TG_CUSTOMAPI)
        .get_updates_connect_timeout(60)
        .connect_timeout(60)
        .get_updates_read_timeout(60)
        .read_timeout(60)
        .get_updates_write_timeout(60)
        .write_timeout(60)
        .build()
    )

    if TG_SINGLE_MODE:
        from submit_single import confirm_submit_handler, submission_handler

        application.add_handler(confirm_submit_handler)
    else:
        from submit import submission_handler

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
            CallbackQueryHandler(
                query_decision, pattern=f"^{ReviewChoice.QUERY}"
            ),
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
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP))
                & (
                    PrefixFilter("/append ")
                    | PrefixFilter(f"@{TG_BOT_USERNAME} /append ")
                ),
                append_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP))
                & (
                    PrefixFilter("/remove_append ")
                    | PrefixFilter(f"@{TG_BOT_USERNAME} /remove_append ")
                ),
                remove_append_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP))
                & (
                    PrefixFilter("/comment ")
                    | PrefixFilter(f"@{TG_BOT_USERNAME} /comment ")
                ),
                comment_message,
            ),
            MessageHandler(
                filters.REPLY
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP))
                & (
                    PrefixFilter("/reject ")
                    | PrefixFilter(f"@{TG_BOT_USERNAME} /reject ")
                ),
                send_custom_rejection_reason,
            ),
            CommandHandler(
                "ban",
                ban_user,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "unban",
                unban_user,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "listban",
                list_banned_users,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "ban_origin",
                ban_origin,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "unban_origin",
                unban_origin,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "listban_origin",
                list_banned_origins,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "stats",
                submitter_stats,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            ),
            CommandHandler(
                "reviewer_stats",
                reviewer_stats,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            ),
            CommandHandler(
                "limit",
                get_set_submitter_max_submission_per_hour,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "limit_reset",
                reset_submitter_max_submission_per_hour,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
            CommandHandler(
                "limit_default",
                get_set_default_max_submission_per_hour,
                filters=~filters.UpdateType.EDITED_MESSAGE
                & filters.Chat(chat_id=int(TG_REVIEWER_GROUP)),
            ),
        ]
    )
    application.run_polling()
