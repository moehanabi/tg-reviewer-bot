from textwrap import dedent
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from utils import TG_PUBLISH_CHANNEL, TG_REJECTED_CHANNEL, APPROVE_NUMBER_REQUIRED, REJECT_NUMBER_REQUIRED, REJECTION_REASON, send_submission, send_result_to_submitter
import pickle
import base64

'''
submission_meta = {
    "submitter": [submitter.id, submitter.username, submitter.full_name, first_submission_message.id],
    "reviewer": {
        reviewer1.id: [reviewer1.username, reviewer1.full_name, option1],
        reviewer2.id: [reviewer2.username, reviewer2.full_name, option2],
        ...
    },
    "media_id_list": [media1.id, media2.id, ...],
    "media_type_list": [media1.type, media2.type, ...],
    "documents_id_list": [document1.id, document2.id, ...],
    "document_type_list": [document1.type, document2.type, ...],
    "append": {
        reviewer1.full_name: ["审核注：...", ...],
        reviewer1.full_name: ["审核注：...", ...],
    },
}
'''


class ReviewChoice:
    SFW = '0'
    NSFW = '1'
    REJECT = '2'
    REJECT_DUPLICATE = '3'
    QUERY = '4'
    WITHDRAW = '5'
    APPEND = '6'


class SubmissionStatus:
    PENDING = 0
    APPROVED = 1
    REJECTED = 2
    REJECTED_NO_REASON = 3


async def reply_review_message(first_submission_message, submission_meta):
    # reply the first submission_message and show the inline keyboard to let the reviewers to decide whether to publish it
    inline_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟢 通过", callback_data=f"{ReviewChoice.SFW}.{first_submission_message.message_id}"),
                InlineKeyboardButton(
                    "🟡 以 NSFW 通过", callback_data=f"{ReviewChoice.NSFW}.{first_submission_message.message_id}")
            ],
            [
                InlineKeyboardButton(
                    "🔴 拒绝", callback_data=f"{ReviewChoice.REJECT}.{first_submission_message.message_id}"),
                InlineKeyboardButton(
                    "🔴 以重复投稿拒绝", callback_data=f"{ReviewChoice.REJECT_DUPLICATE}.{first_submission_message.message_id}"),
            ],
            [
                InlineKeyboardButton(
                    "❔ 查询我的投票", callback_data=f"{ReviewChoice.QUERY}.{first_submission_message.message_id}"),
                InlineKeyboardButton(
                    "↩️ 撤回我的投票", callback_data=f"{ReviewChoice.WITHDRAW}.{first_submission_message.message_id}")
            ],
            [
                InlineKeyboardButton(
                    "📝 添加备注", switch_inline_query_current_chat="/append 请回复原消息并修改此处文字"),
                InlineKeyboardButton(
                    "⬅️ 删除备注", switch_inline_query_current_chat="/remove_append 请回复原消息并修改此处文字为待删除备注的编号")
            ],
            [
                InlineKeyboardButton(
                    "💬 回复投稿人", switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字"),
            ]
        ]
    )

    await first_submission_message.reply_text(generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=inline_keyboard)


async def approve_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    action = query.data.split('.')[0]
    review_message = update.effective_message
    origin_message = review_message.reply_to_message

    reviewer_id, reviewer_username, reviewer_fullname = query.from_user.id, query.from_user.username, query.from_user.full_name
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))

    # if the reviewer has already approved or rejected the submission
    if reviewer_id in list(submission_meta['reviewer']):
        await query_decision(update, context)
        return

    # if the reviewer has not approved or rejected the submission
    submission_meta['reviewer'][reviewer_id] = [
        reviewer_username, reviewer_fullname, action]
    # get options from all reviewers
    review_options = [reviewer[2]
                      for reviewer in submission_meta['reviewer'].values()]
    # if the submission has not been approved by enough reviewers
    if review_options.count(ReviewChoice.NSFW) + review_options.count(ReviewChoice.SFW) < APPROVE_NUMBER_REQUIRED:
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=review_message.reply_markup)
        await query.answer(f"✅ 投票成功！{get_decision(submission_meta, reviewer_id)}")
        return
    # else if the submission has been approved by enough reviewers
    await query.answer("✅ 投票成功，此条投稿已通过")
    # send result to submitter
    await send_result_to_submitter(context, submission_meta['submitter'][0], submission_meta['submitter'][3], "🎉 恭喜，投稿已通过审核")
    # then send this submission to the publish channel
    # if the submission is nsfw
    skip_all = None
    has_spoiler = False
    if ReviewChoice.NSFW in review_options:
        has_spoiler = True
        inline_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("跳到下一条", url=f'https://t.me/')]])
        skip_all = await context.bot.send_message(
            chat_id=TG_PUBLISH_CHANNEL, text="⚠️ #NSFW 提前预警", reply_markup=inline_keyboard)
    # get all append messages from submission_meta['append']
    append_messages = []
    for append_list in submission_meta['append'].values():
        append_messages.extend(append_list)
    append_messages_string = "\n".join(append_messages)
    sent_messages = await send_submission(context=context, chat_id=TG_PUBLISH_CHANNEL, media_id_list=submission_meta['media_id_list'], media_type_list=submission_meta['media_type_list'], documents_id_list=submission_meta['documents_id_list'], document_type_list=submission_meta['document_type_list'], text=((origin_message.text or origin_message.caption) or '') + "\n" + append_messages_string, has_spoiler=has_spoiler)
    # edit the skip_all message
    if skip_all:
        url_parts = sent_messages[-1].link.rsplit('/', 1)
        next_url = url_parts[0] + '/' + str(int(url_parts[-1]) + 1)
        inline_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("跳到下一条", url=next_url)]])
        await skip_all.edit_text(text="⚠️ #NSFW 提前预警", reply_markup=inline_keyboard)
    # add inline keyboard to jump to this submission and its comments in the publish channel
    inline_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("在频道中查看", url=sent_messages[0].link),
          InlineKeyboardButton("查看评论区", url=f"{sent_messages[0].link}?comment=1")],
         [InlineKeyboardButton("💬 回复投稿人", switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字")]])
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=inline_keyboard)


async def reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    review_message = update.effective_message
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))
    # if the reviewer has not rejected the submission
    if query.from_user.id not in submission_meta['reviewer'] or submission_meta['reviewer'][query.from_user.id][2] != ReviewChoice.REJECT:
        await query.answer("😂 你没有投拒绝票")
        return

    # if the reviewer has rejected the submission
    match query.data:
        case "REASON.NONE":
            submission_meta['reviewer'][query.from_user.id][2] = len(
                REJECTION_REASON)
        case "REASON.OTHER":
            await query.answer("😂 只要回复本条消息并附上理由即可", show_alert=True)
            return
        case _:
            submission_meta['reviewer'][query.from_user.id][2] = int(
                query.data.split('.')[1])
    await query.answer()
    inline_keyboard = None
    if TG_REJECTED_CHANNEL:
        inline_keyboard = InlineKeyboardMarkup(
            [review_message.reply_markup.inline_keyboard[-2:]])
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=inline_keyboard)
    # send result to submitter
    await send_result_to_submitter(context, submission_meta['submitter'][0], submission_meta['submitter'][3], f"😢 很抱歉，投稿未通过审核。\n原因：{get_rejection_reason_text(submission_meta['reviewer'][query.from_user.id][2])}")


async def reject_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    action = query.data.split('.')[0]
    review_message = update.effective_message
    origin_message = review_message.reply_to_message
    reviewer_id, reviewer_username, reviewer_fullname = query.from_user.id, query.from_user.username, query.from_user.full_name
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))

    # get all append messages from submission_meta['append']
    append_messages = []
    for append_list in submission_meta['append'].values():
        append_messages.extend(append_list)
    append_messages_string = "\n".join(append_messages)

    # if REJECT_DUPLICATE, only one reviewer is enough
    if action == ReviewChoice.REJECT_DUPLICATE:
        # if the reviewer has already approved or rejected the submission, remove the previous decision
        submission_meta, _ = remove_decision(submission_meta, reviewer_id)
        submission_meta['reviewer'][reviewer_id] = [
            reviewer_username, reviewer_fullname, action]
        await query.answer("✅ 投票成功，此条投稿已被拒绝")
        # send the submittion to rejected channel
        inline_keyboard = None
        if TG_REJECTED_CHANNEL:
            sent_message = await send_submission(context=context, chat_id=TG_REJECTED_CHANNEL, media_id_list=submission_meta['media_id_list'], media_type_list=submission_meta['media_type_list'], documents_id_list=submission_meta['documents_id_list'], document_type_list=submission_meta['document_type_list'], text=((origin_message.text or origin_message.caption) or '') + "\n" + append_messages_string)
            inline_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("在拒稿频道中查看", url=sent_message[-1].link)],
                 [InlineKeyboardButton("💬 回复投稿人", switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字")]])
        await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=inline_keyboard)
        # send result to submitter
        await send_result_to_submitter(context, submission_meta['submitter'][0], submission_meta['submitter'][3], f"😢 很抱歉，投稿未通过审核。\n原因：{get_rejection_reason_text(submission_meta['reviewer'][query.from_user.id][2])}")
        return
    # else if the reviewer has already approved or rejected the submission
    if reviewer_id in list(submission_meta['reviewer']):
        await query_decision(update, context)
        return
    # else if the reviewer has not approved or rejected the submission
    submission_meta['reviewer'][reviewer_id] = [
        reviewer_username, reviewer_fullname, action]
    # get options from all reviewers
    review_options = [reviewer[2]
                      for reviewer in submission_meta['reviewer'].values()]
    # if the submission has not been rejected by enough reviewers
    if review_options.count(ReviewChoice.REJECT) < REJECT_NUMBER_REQUIRED:
        await review_message.edit_text(
            text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=review_message.reply_markup)
        await query.answer(f"✅ 投票成功！{get_decision(submission_meta, reviewer_id)}")
        return
    # else if the submission has been rejected by enough reviewers
    await query.answer("✅ 投票成功，此条投稿已被拒绝")
    # send the rejection reason options inline keyboard
    # show inline keyboard in 2 cols
    inline_keyboard_content = []
    for i in range(0, len(REJECTION_REASON), 2):
        inline_keyboard_content.append(
            [InlineKeyboardButton(REJECTION_REASON[i], callback_data=f"REASON.{i}")])
        if i+1 < len(REJECTION_REASON):
            inline_keyboard_content[-1].append(
                InlineKeyboardButton(REJECTION_REASON[i+1], callback_data=f"REASON.{i+1}"))
    inline_keyboard_content.append([
        InlineKeyboardButton("自定义理由", callback_data="REASON.OTHER"),
        InlineKeyboardButton("暂无理由", callback_data="REASON.NONE")
    ])
    # send the submittion to rejected channel
    if TG_REJECTED_CHANNEL:
        sent_message = await send_submission(context=context, chat_id=TG_REJECTED_CHANNEL, media_id_list=submission_meta['media_id_list'], media_type_list=submission_meta['media_type_list'], documents_id_list=submission_meta['documents_id_list'], document_type_list=submission_meta['document_type_list'], text=((origin_message.text or origin_message.caption) or '') + "\n" + append_messages_string)
        inline_keyboard_content.extend(
            [[InlineKeyboardButton("在拒稿频道中查看", url=sent_message[-1].link)],
             [InlineKeyboardButton("💬 回复投稿人", switch_inline_query_current_chat="/comment 请回复原消息并修改此处文字")]])
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(inline_keyboard_content))


async def append_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    append_message = update.message.text.split('/append ')[1]
    if not update.message.reply_to_message:
        return
    review_message = update.message.reply_to_message
    # if there is not a submission_meta in the review_message
    if '\u200b' not in review_message.text:
        return
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))
    if get_submission_status(submission_meta)[0] != SubmissionStatus.PENDING:
        await update.message.reply_text("😂 只有待审稿件才能添加备注")
        return
    reviewer_fullname = update.message.from_user.full_name
    if reviewer_fullname not in submission_meta['append']:
        submission_meta['append'][reviewer_fullname] = []
    submission_meta['append'][reviewer_fullname].append(
        f"审核注：{append_message}")
    await update.message.reply_text("✅ 已添加备注")
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=review_message.reply_markup)

async def remove_append_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    append_message_num = update.message.text.split('/remove_append ')[1]
    if not update.message.reply_to_message:
        return
    review_message = update.message.reply_to_message
    # if there is not a submission_meta in the review_message
    if '\u200b' not in review_message.text:
        return
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))
    if get_submission_status(submission_meta)[0] != SubmissionStatus.PENDING:
        await update.message.reply_text("😂 只有待审稿件才能删除备注")
        return
    reviewer_fullname = update.message.from_user.full_name
    if reviewer_fullname not in submission_meta['append']:
        await update.message.reply_text("😂 你没有添加备注")
        return
    try:
        append_message_num = int(append_message_num)
    except:
        await update.message.reply_text("😂 请输入正确的备注序号")
        return
    if append_message_num < 1 or append_message_num > len(submission_meta['append'][reviewer_fullname]):
        await update.message.reply_text("😂 请输入正确的备注序号")
        return
    submission_meta['append'][reviewer_fullname].pop(append_message_num - 1)
    await update.message.reply_text("✅ 已删除备注")
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=review_message.reply_markup)

async def comment_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment_message = update.message.text.split('/comment ')[1]
    if not update.message.reply_to_message:
        return
    review_message = update.message.reply_to_message
    # if there is not a submission_meta in the review_message
    if '\u200b' not in review_message.text:
        return
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))
    await send_result_to_submitter(context, submission_meta['submitter'][0], submission_meta['submitter'][3], f"来自审核的消息：{comment_message}")
    await update.message.reply_text("✅ 已发送")


async def send_custom_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
    review_message = update.message.reply_to_message
    # if there is not a submission_meta in the review_message
    if '\u200b' not in review_message.text:
        return
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))
    # if the submission has not been rejected yet
    if get_submission_status(submission_meta)[0] not in [SubmissionStatus.REJECTED_NO_REASON, SubmissionStatus.REJECTED]:
        return
    # if the reviewer has not rejected the submission
    if update.message.from_user.id not in submission_meta['reviewer'] or submission_meta['reviewer'][update.message.from_user.id][2] in [ReviewChoice.SFW, ReviewChoice.NSFW]:
        await update.message.reply_text("😂 你没有投拒绝票")
        return
    # if the reviewer has rejected the duplicate submission without other reviewer rejecting it
    options = [reviewer[2]
               for reviewer in submission_meta['reviewer'].values()]
    approve_num = options.count(ReviewChoice.NSFW) + \
        options.count(ReviewChoice.SFW)
    if submission_meta['reviewer'][update.message.from_user.id][2] == ReviewChoice.REJECT_DUPLICATE and approve_num + 1 == len(options):
        await update.message.reply_text("😢 重复投稿一票否决不可修改理由")
        return
    # if the reason has not been changed
    if submission_meta['reviewer'][update.message.from_user.id][2] == update.message.text:
        return

    submission_meta['reviewer'][update.message.from_user.id][2] = update.message.text
    inline_keyboard = None
    if TG_REJECTED_CHANNEL:
        inline_keyboard = InlineKeyboardMarkup(
            [review_message.reply_markup.inline_keyboard[-1]])
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=inline_keyboard)

    # send result to submitter
    await send_result_to_submitter(context, submission_meta['submitter'][0], submission_meta['submitter'][3], f"😢 很抱歉，投稿未通过审核。\n原因：{update.message.text}")
    # delete the custom rejection reason message if the bot can
    try:
        await update.message.delete()
    except:
        pass


def get_decision(submission_meta, reviewer):
    if reviewer not in submission_meta['reviewer']:
        return '😂 你还没有投票'
    choice = '你已经选择了：'
    match submission_meta['reviewer'][reviewer][2]:
        case ReviewChoice.SFW:
            choice += '🟢 通过'
        case ReviewChoice.NSFW:
            choice += '🟡 以 NSFW 通过'
        case ReviewChoice.REJECT:
            choice += '🔴 拒绝'
    return choice


async def query_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    review_message = update.effective_message
    reviewer = query.from_user.id
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))

    await query.answer(get_decision(submission_meta, reviewer))


def remove_decision(submission_meta, reviewer):
    if reviewer in submission_meta['reviewer']:
        del submission_meta['reviewer'][reviewer]
        return submission_meta, True
    else:
        return submission_meta, False


async def withdraw_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    review_message = update.effective_message
    reviewer = query.from_user.id
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text_markdown_v2_urled.split('/')[-1][:-1]))

    submission_meta, removed = remove_decision(submission_meta, reviewer)
    if removed:
        await review_message.edit_text(text=generate_submission_meta_string(submission_meta), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=review_message.reply_markup)
        await query.answer("↩️ 已撤回")
    else:
        await query.answer("😂 你还没有投票")


def get_rejection_reason_text(option):
    # rejection reason is an int value, see reject_reason()
    if isinstance(option, int):
        if option < len(REJECTION_REASON):
            option_text = REJECTION_REASON[option]
        elif option == len(REJECTION_REASON):
            option_text = "暂无理由"
    elif option == ReviewChoice.REJECT_DUPLICATE:
        option_text = "已在频道发布过或已有人投稿过"
    else:
        option_text = option
    return option_text


def get_submission_status(submission_meta):
    status = -1
    rejection_reason = ""
    review_options = [reviewer[2]
                      for reviewer in submission_meta['reviewer'].values()]
    if review_options.count(ReviewChoice.NSFW) + review_options.count(ReviewChoice.SFW) >= APPROVE_NUMBER_REQUIRED:
        status = SubmissionStatus.APPROVED
    elif review_options.count(ReviewChoice.REJECT) >= REJECT_NUMBER_REQUIRED:
        status = SubmissionStatus.REJECTED_NO_REASON
    elif ReviewChoice.REJECT_DUPLICATE in review_options or review_options.count(ReviewChoice.NSFW) + review_options.count(ReviewChoice.SFW) + review_options.count(ReviewChoice.REJECT) < len(review_options):
        # At least one reviewer has given rejection reason
        status = SubmissionStatus.REJECTED
        for review_option in review_options:
            if review_option not in [ReviewChoice.NSFW, ReviewChoice.SFW, ReviewChoice.REJECT]:
                rejection_reason = get_rejection_reason_text(review_option)
                break
    else:
        status = SubmissionStatus.PENDING
    return status, rejection_reason


def generate_submission_meta_string(submission_meta):
    # generate the submission_meta string from the submission_meta
    # approved submission string style:
    '''
    ✅ An approved submission

    Submitter: submitter.full_name (@submitter.username, submitter.id)
    Reviewers: 
    - 🔴 Rejected by reviewer1.full_name (@reviewer1.username, reviewer1.id)
    - 🟢 Approved as SFW by reviewer2.full_name (@reviewer2.username, reviewer2.id)
    - 🟢 Approved as SFW by reviewer3.full_name (@reviewer3.username, reviewer3.id)
    Status: Approved as SFW

    #ABI_VER_6 #USER_submitter.id #SUBMITTER_submitter.id #SUBMITTER_UNSIGNED #USER_reviewer1.id #REVIEWER_reviewer1.id #USER_reviewer2.id #REVIEWER_reviewer2.id #USER_reviewer3.id #REVIEWER_reviewer3.id #APPROVED #SFW
    '''
    # rejected submission string style:
    '''
    ❌ A rejected submission

    Submitter: submitter.full_name (@submitter.username, submitter.id)
    Reviewers: 
    - 🟢 Approved as SFW by reviewer1.full_name (@reviewer1.username, reviewer1.id)
    - 🔴 Rejected by reviewer2.full_name (@reviewer2.username, reviewer2.id)
    - 🔴 Rejected as 内容不够有趣 by reviewer3.full_name (@reviewer3.username, reviewer3.id)
    Status: Rejected as 内容不够有趣

    #ABI_VER_6 #USER_submitter.id #SUBMITTER_submitter.id #SUBMITTER_SIGNED #REVIEWER_reviewer1.id #USER_reviewer2.id #REVIEWER_reviewer2.id #USER_reviewer3.id #REVIEWER_reviewer3.id #REJECTED
    '''

    # rejected but no reason chosen submission string style:
    '''
    ❔ A pending review submission

    Submitter: submitter.full_name (@submitter.username, submitter.id)
    Reviewers: 
    - 🔴 Rejected by reviewer1.full_name (@reviewer1.username, reviewer1.id)
    - 🔴 Rejected by reviewer2.full_name (@reviewer2.username, reviewer2.id)
    Status: Pending

    #ABI_VER_6 #USER_submitter.id #SUBMITTER_submitter.id #SUBMITTER_UNSIGNED #USER_reviewer1.id #REVIEWER_reviewer1.id #USER_reviewer2.id #REVIEWER_reviewer2.id #PENDING
    '''

    # pending submission string style:
    '''
    ❔ A pending review submission

    Submitter: submitter.full_name (@submitter.username, submitter.id)
    Reviewer: Hidden until the final results of the review vote
    Status: Pending

    #ABI_VER_6 #USER_submitter.id #SUBMITTER_submitter.id #SUBMITTER_UNSIGNED #PENDING
    '''

    # get status and rejection reason
    status, rejection_reason = get_submission_status(submission_meta)
    # submitter_string
    submitter_id, submitter_username, submitter_fullname, _ = submission_meta['submitter']
    submitter_string = f"投稿人：{submitter_fullname} ({f'@{submitter_username}, ' if submitter_username else ''}{submitter_id})\n"

    # reviewers_string
    is_nsfw = False
    reviewers_string = "审稿人："
    if status == SubmissionStatus.PENDING:
        reviewers_string += "在结果公布前暂时隐藏"
    else:
        for reviewer_id, [reviewer_username, reviewer_fullname, option] in submission_meta['reviewer'].items():
            option_text = ""
            option_sign = ""
            match option:
                case ReviewChoice.SFW:
                    option_text = "以 SFW 通过"
                    option_sign = "🟢"
                case ReviewChoice.NSFW:
                    option_text = "以 NSFW 通过"
                    option_sign = "🟡"
                    is_nsfw = True
                case ReviewChoice.REJECT:
                    option_text = "拒稿"
                    option_sign = "🔴"
                case _:
                    option_text = f"因为 {get_rejection_reason_text(option)} 拒稿"
                    option_sign = "🔴"
            reviewers_string += f"\n- {option_sign} 由 {reviewer_fullname} ({f'@{reviewer_username}, ' if reviewer_username else ''}{reviewer_id}) {option_text}"

    # append_string
    append_string = "审稿人备注："
    for reviewer_fullname, append_list in submission_meta['append'].items():
        append_string += f"\n - 由 {reviewer_fullname} 添加的备注："
        append_string += ''.join(f"\n{i+1}. {message}" for i, message in enumerate(append_list))

    # status_string and status_tag
    status_string = ""
    status_tag = ""
    match status:
        case SubmissionStatus.PENDING:
            status_string = "待审稿"
            status_tag = "#PENDING"
        case SubmissionStatus.APPROVED:
            status_string = "以 SFW 通过" if is_nsfw else "以 NSFW 通过"
            status_tag = "#APPROVED #SFW" if not is_nsfw else "#APPROVED #NSFW"
        case SubmissionStatus.REJECTED:
            status_string = f"因为 {rejection_reason} 被拒稿"
            status_tag = "#REJECTED"
        case SubmissionStatus.REJECTED_NO_REASON:
            status_string = "被拒稿，待选择理由"
            status_tag = "#PENDING_FOR_REASON"

    # status_title
    status_title = "❔ 待审稿件" if status == SubmissionStatus.PENDING else (
        "✅ 已通过稿件" if status == SubmissionStatus.APPROVED else "❌ 已拒绝稿件")
    # tags
    tags = f"#USER_{submitter_id} #SUBMITTER_{submitter_id}"
    if status != SubmissionStatus.PENDING:
        for reviewer_id in submission_meta['reviewer'].keys():
            tags += f" #USER_{reviewer_id} #REVIEWER_{reviewer_id}"
    tags += f" {status_tag}"

    submission_meta_text = f"[\u200b](http://t.me/{base64.urlsafe_b64encode(pickle.dumps(submission_meta)).decode()})" if status != SubmissionStatus.APPROVED else ""
    visible_content = escape_markdown(dedent(f'''\
{status_title}

{submitter_string}
{reviewers_string}
{append_string}
当前状态：{status_string}

{tags}'''), version=2)
    # use Zero-width non-joiner and fake url(or the bot api will delete invalid link) to hide the submission_meta
    return f"{visible_content}{submission_meta_text}"
