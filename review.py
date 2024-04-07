import base64
import pickle

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from review_utils import (
    ReviewChoice,
    generate_submission_meta_string,
    get_decision,
    get_rejection_reason_text,
    remove_decision,
    send_result_to_submitter,
)
from utils import (
    APPROVE_NUMBER_REQUIRED,
    REJECT_NUMBER_REQUIRED,
    REJECTION_REASON,
    TG_PUBLISH_CHANNEL,
    TG_REJECTED_CHANNEL,
    send_result_to_submitter,
    send_submission,
)


async def approve_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    action = query.data.split(".")[0]
    review_message = update.effective_message
    origin_message = review_message.reply_to_message

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

    # if the reviewer has already approved or rejected the submission
    if reviewer_id in list(submission_meta["reviewer"]):
        await query_decision(update, context)
        return

    # if the reviewer has not approved or rejected the submission
    submission_meta["reviewer"][reviewer_id] = [
        reviewer_username,
        reviewer_fullname,
        action,
    ]
    # get options from all reviewers
    review_options = [
        reviewer[2] for reviewer in submission_meta["reviewer"].values()
    ]
    # if the submission has not been approved by enough reviewers
    if (
        review_options.count(ReviewChoice.NSFW)
        + review_options.count(ReviewChoice.SFW)
        < APPROVE_NUMBER_REQUIRED
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
    # send result to submitter
    await send_result_to_submitter(
        context,
        submission_meta["submitter"][0],
        submission_meta["submitter"][3],
        "🎉 恭喜，投稿已通过审核",
    )
    # then send this submission to the publish channel
    # if the submission is nsfw
    skip_all = None
    has_spoiler = False
    if ReviewChoice.NSFW in review_options:
        has_spoiler = True
        inline_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("跳到下一条", url=f"https://t.me/")]]
        )
        skip_all = await context.bot.send_message(
            chat_id=TG_PUBLISH_CHANNEL,
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
        chat_id=TG_PUBLISH_CHANNEL,
        media_id_list=submission_meta["media_id_list"],
        media_type_list=submission_meta["media_type_list"],
        documents_id_list=submission_meta["documents_id_list"],
        document_type_list=submission_meta["document_type_list"],
        text=((origin_message.text or origin_message.caption) or "")
        + "\n"
        + append_messages_string,
        has_spoiler=has_spoiler,
    )
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
    inline_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "在频道中查看", url=sent_messages[0].link
                ),
                InlineKeyboardButton(
                    "查看评论区", url=f"{sent_messages[0].link}?comment=1"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💬 回复投稿人",
                    switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字",
                )
            ],
        ]
    )
    await review_message.edit_text(
        text=generate_submission_meta_string(submission_meta),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=inline_keyboard,
    )


async def reject_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    action = query.data.split(".")[0]
    review_message = update.effective_message
    origin_message = review_message.reply_to_message
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

    # get all append messages from submission_meta['append']
    append_messages = []
    for append_list in submission_meta["append"].values():
        append_messages.extend(append_list)
    append_messages_string = "\n".join(append_messages)

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
        # send the submittion to rejected channel
        inline_keyboard = None
        if TG_REJECTED_CHANNEL:
            sent_message = await send_submission(
                context=context,
                chat_id=TG_REJECTED_CHANNEL,
                media_id_list=submission_meta["media_id_list"],
                media_type_list=submission_meta["media_type_list"],
                documents_id_list=submission_meta["documents_id_list"],
                document_type_list=submission_meta["document_type_list"],
                text=((origin_message.text or origin_message.caption) or "")
                + "\n"
                + append_messages_string,
            )
            inline_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "在拒稿频道中查看", url=sent_message[-1].link
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "💬 回复投稿人",
                            switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字",
                        )
                    ],
                ]
            )
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=inline_keyboard,
        )
        # send result to submitter
        await send_result_to_submitter(
            context,
            submission_meta["submitter"][0],
            submission_meta["submitter"][3],
            f"😢 很抱歉，投稿未通过审核。\n原因：{get_rejection_reason_text(submission_meta['reviewer'][query.from_user.id][2])}",
        )
        return
    # else if the reviewer has already approved or rejected the submission
    if reviewer_id in list(submission_meta["reviewer"]):
        await query_decision(update, context)
        return
    # else if the reviewer has not approved or rejected the submission
    submission_meta["reviewer"][reviewer_id] = [
        reviewer_username,
        reviewer_fullname,
        action,
    ]
    # get options from all reviewers
    review_options = [
        reviewer[2] for reviewer in submission_meta["reviewer"].values()
    ]
    # if the submission has not been rejected by enough reviewers
    if review_options.count(ReviewChoice.REJECT) < REJECT_NUMBER_REQUIRED:
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
                switch_inline_query_current_chat="/reject 请回复原消息并修改此处文字",
            ),
            InlineKeyboardButton("暂无理由", callback_data="REASON.NONE"),
        ]
    )
    # send the submittion to rejected channel
    if TG_REJECTED_CHANNEL:
        sent_message = await send_submission(
            context=context,
            chat_id=TG_REJECTED_CHANNEL,
            media_id_list=submission_meta["media_id_list"],
            media_type_list=submission_meta["media_type_list"],
            documents_id_list=submission_meta["documents_id_list"],
            document_type_list=submission_meta["document_type_list"],
            text=((origin_message.text or origin_message.caption) or "")
            + "\n"
            + append_messages_string,
        )
        inline_keyboard_content.extend(
            [
                [
                    InlineKeyboardButton(
                        "在拒稿频道中查看", url=sent_message[-1].link
                    )
                ],
                [
                    InlineKeyboardButton(
                        "💬 回复投稿人",
                        switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字",
                    )
                ],
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
