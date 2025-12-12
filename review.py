import base64
import pickle
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from db_op import Reviewer, Submitter
from env import (
    APPROVE_NUMBER_REQUIRED,
    REJECT_NUMBER_REQUIRED,
    REJECTION_REASON,
    TG_PUBLISH_CHANNEL,
    TG_SELF_APPROVE,
    TG_TIMEOUT_SINGLEREVIEW,
)
from review_utils import (
    ReviewChoice,
    generate_submission_meta_string,
    get_decision,
    remove_decision,
    send_to_rejected_channel,
)
from utils import send_result_to_submitter, send_submission


async def approve_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    action = query.data.split(".")[0]
    review_message = update.effective_message

    reviewer_id, reviewer_username, reviewer_fullname = (
        query.from_user.id,
        query.from_user.username,
        query.from_user.full_name,
    )
    submission_meta = pickle.loads(
        base64.urlsafe_b64decode(
            review_message.text_markdown_v2_urled.split("/")[-1][:-1]
        )
    )

    submission_longago = (datetime.now(timezone.utc) - update.effective_message.date > timedelta(minutes=TG_TIMEOUT_SINGLEREVIEW))
    already_choose = False
    # if the reviewer has already rejected the submission
    if reviewer_id in list(submission_meta["reviewer"]):
        already_choose = True
        if submission_meta["reviewer"][reviewer_id][2] not in [
            ReviewChoice.SFW,
            ReviewChoice.NSFW,
        ]:
            await query_decision(update, context)
            return

    # if the reviwer is the submitter
    if not TG_SELF_APPROVE and reviewer_id == submission_meta["submitter"][0]:
        await query.answer("❌ 你不能给自己投通过票")
        return

    # if the reviewer has not rejected the submission
    submission_meta["reviewer"][reviewer_id] = [
        reviewer_username,
        reviewer_fullname,
        action,
    ]

    # increse reviewer approve count
    if not already_choose:
        Reviewer.count_increase(reviewer_id, "approve_count")

    # get options from all reviewers
    review_options = [
        reviewer[2] for reviewer in submission_meta["reviewer"].values()
    ]
    # if the submission has not been approved by enough reviewers
    if (
        (review_options.count(ReviewChoice.NSFW) + review_options.count(ReviewChoice.SFW) < APPROVE_NUMBER_REQUIRED)
        and not submission_longago
    ):
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=review_message.reply_markup,
        )
        await query.answer(
            f"✅ 投票成功！{get_decision(submission_meta, reviewer_id)}"
        )
        return
    # else if the submission has been approved by enough reviewers
    await query.answer("✅ 投票成功，此条投稿已通过")
    # increse submitter approved count
    Submitter.count_increase(submission_meta["submitter"][0], "approved_count")
    # increse reviewer count
    for reviewer_id in submission_meta["reviewer"]:
        if submission_meta["reviewer"][reviewer_id][2] not in [
            ReviewChoice.SFW,
            ReviewChoice.NSFW,
        ]:
            Reviewer.count_increase(reviewer_id, "reject_but_approved_count")
    # then send this submission to the publish channel
    main_channel_messages = None
    submission_meta["sent_msg"] = {}
    for publish_channel in TG_PUBLISH_CHANNEL:
        # if the submission is nsfw
        skip_all = None
        has_spoiler = False
        if ReviewChoice.NSFW in review_options:
            has_spoiler = True
            inline_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("跳到下一条", url=f"https://t.me/")]]
            )
            skip_all = await context.bot.send_message(
                chat_id=publish_channel,
                text="⚠️ #NSFW 提前预警",
                reply_markup=inline_keyboard,
            )
        # get all append messages from submission_meta['append']
        append_messages = []
        for append_list in submission_meta["append"].values():
            append_messages.extend(append_list)
        append_messages_string = "\n".join(append_messages)
        sent_messages = await send_submission(
            context=context,
            chat_id=publish_channel,
            media_id_list=submission_meta["media_id_list"],
            media_type_list=submission_meta["media_type_list"],
            documents_id_list=submission_meta["documents_id_list"],
            document_type_list=submission_meta["document_type_list"],
            text=submission_meta["text"] + "\n" + append_messages_string,
            has_spoiler=has_spoiler,
        )
        if main_channel_messages is None:
            main_channel_messages = sent_messages
        # edit the skip_all message
        if skip_all:
            url_parts = sent_messages[-1].link.rsplit("/", 1)
            next_url = url_parts[0] + "/" + str(int(url_parts[-1]) + 1)
            inline_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("跳到下一条", url=next_url)]]
            )
            await skip_all.edit_text(
                text="⚠️ #NSFW 提前预警", reply_markup=inline_keyboard
            )
        # add inline keyboard to jump to this submission and its comments in the publish channel
        sent_message_ids = [message.message_id for message in sent_messages]
        if skip_all is not None:
            sent_message_ids.append(skip_all.message_id)
        submission_meta["sent_msg"][publish_channel] = sent_message_ids

    inline_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "在频道中查看", url=main_channel_messages[0].link
                ),
                InlineKeyboardButton(
                    "查看评论区",
                    url=f"{main_channel_messages[0].link}?comment=1",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💬 回复投稿人",
                    switch_inline_query_current_chat="/comment ",
                ),
                InlineKeyboardButton(
                    "↩️ 撤稿",
                    callback_data=f"{ReviewChoice.APPROVED_RETRACT}",
                ),
            ],
        ]
    )
    await review_message.edit_text(
        text=generate_submission_meta_string(submission_meta,longago_approve=submission_longago),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=inline_keyboard,
    )
    # send result to submitter
    await send_result_to_submitter(
        context,
        submission_meta["submitter"][0],
        submission_meta["submitter"][3],
        "🎉 恭喜，投稿已通过审核",
        inline_keyboard_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "在频道中查看", url=main_channel_messages[0].link
                    ),
                    InlineKeyboardButton(
                        "查看评论区",
                        url=f"{main_channel_messages[0].link}?comment=1",
                    ),
                ]
            ]
        ),
    )


async def reject_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    action = query.data.split(".")[0]
    review_message = update.effective_message
    reviewer_id, reviewer_username, reviewer_fullname = (
        query.from_user.id,
        query.from_user.username,
        query.from_user.full_name,
    )
    submission_meta = pickle.loads(
        base64.urlsafe_b64decode(
            review_message.text_markdown_v2_urled.split("/")[-1][:-1]
        )
    )

    submission_longago = (datetime.now(timezone.utc) - update.effective_message.date > timedelta(minutes=TG_TIMEOUT_SINGLEREVIEW))
    # if REJECT_DUPLICATE, only one reviewer is enough
    if action == ReviewChoice.REJECT_DUPLICATE:
        # if the reviewer has already approved or rejected the submission, remove the previous decision
        submission_meta, _ = remove_decision(submission_meta, reviewer_id)
        submission_meta["reviewer"][reviewer_id] = [
            reviewer_username,
            reviewer_fullname,
            action,
        ]
        await query.answer("✅ 投票成功，此条投稿已被拒绝")
        inline_keyboard_content = []
        inline_keyboard_content.append(
            [
                InlineKeyboardButton(
                    "💬 回复投稿人",
                    switch_inline_query_current_chat="/comment ",
                )
            ]
        )
        # send the submittion to rejected channel
        await send_to_rejected_channel(
            update=update, context=context, submission_meta=submission_meta
        )

        # increse submitter rejected count
        Submitter.count_increase(
            submission_meta["submitter"][0], "rejected_count"
        )
        # increse reviewer count
        Reviewer.count_increase(reviewer_id, "reject_count")
        for reviewer_id in submission_meta["reviewer"]:
            if submission_meta["reviewer"][reviewer_id][2] in [
                ReviewChoice.SFW,
                ReviewChoice.NSFW,
            ]:
                Reviewer.count_increase(
                    reviewer_id, "approve_but_rejected_count"
                )
        return
    # else if the reviewer has already approved or rejected the submission
    if (reviewer_id in list(submission_meta["reviewer"])) and not submission_longago:
        await query_decision(update, context)
        return
    # else if the reviewer has not approved or rejected the submission
    submission_meta["reviewer"][reviewer_id] = [
        reviewer_username,
        reviewer_fullname,
        action,
    ]
    # increse reviewer reject count
    Reviewer.count_increase(reviewer_id, "reject_count")
    # get options from all reviewers
    review_options = [
        reviewer[2] for reviewer in submission_meta["reviewer"].values()
    ]
    # if the submission has not been rejected by enough reviewers
    if (
        (review_options.count(ReviewChoice.REJECT) < REJECT_NUMBER_REQUIRED)
        and not submission_longago
    ):
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=review_message.reply_markup,
        )
        await query.answer(
            f"✅ 投票成功！{get_decision(submission_meta, reviewer_id)}"
        )
        return
    # else if the submission has been rejected by enough reviewers
    await query.answer("✅ 投票成功，此条投稿已被拒绝")
    # increse submitter rejected count
    Submitter.count_increase(submission_meta["submitter"][0], "rejected_count")
    # increse reviewer count
    for reviewer_id in submission_meta["reviewer"]:
        if submission_meta["reviewer"][reviewer_id][2] in [
            ReviewChoice.SFW,
            ReviewChoice.NSFW,
        ]:
            Reviewer.count_increase(reviewer_id, "approve_but_rejected_count")
    # send the rejection reason options inline keyboard
    # show inline keyboard in 2 cols
    inline_keyboard_content = []
    for i in range(0, len(REJECTION_REASON), 2):
        inline_keyboard_content.append(
            [
                InlineKeyboardButton(
                    REJECTION_REASON[i], callback_data=f"REASON.{i}"
                )
            ]
        )
        if i + 1 < len(REJECTION_REASON):
            inline_keyboard_content[-1].append(
                InlineKeyboardButton(
                    REJECTION_REASON[i + 1], callback_data=f"REASON.{i+1}"
                )
            )
    inline_keyboard_content.append(
        [
            InlineKeyboardButton(
                "自定义理由",
                switch_inline_query_current_chat="/reject ",
            ),
            InlineKeyboardButton("忽略此投稿", callback_data="REASON.IGNORE"),
        ]
    )
    inline_keyboard_content.append(
        [
            InlineKeyboardButton(
                "💬 回复投稿人",
                switch_inline_query_current_chat="/comment ",
            )
        ]
    )
    await review_message.edit_text(
        text=generate_submission_meta_string(submission_meta),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(inline_keyboard_content),
    )


async def query_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    review_message = update.effective_message
    reviewer = query.from_user.id
    submission_meta = pickle.loads(
        base64.urlsafe_b64decode(
            review_message.text_markdown_v2_urled.split("/")[-1][:-1]
        )
    )

    await query.answer(get_decision(submission_meta, reviewer))


async def withdraw_decision(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    review_message = update.effective_message
    reviewer = query.from_user.id
    submission_meta = pickle.loads(
        base64.urlsafe_b64decode(
            review_message.text_markdown_v2_urled.split("/")[-1][:-1]
        )
    )

    submission_meta, removed = remove_decision(submission_meta, reviewer)
    if removed:
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=review_message.reply_markup,
        )
        await query.answer("↩️ 已撤回")
    else:
        await query.answer("😂 你还没有投票")
