from textwrap import dedent
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils import TG_PUBLISH_CHANNEL, APPROVE_NUMBER_REQUIRED, REJECT_NUMBER_REQUIRED, REJECTION_REASON, send_submission
import pickle
import base64

'''
submission_meta = {
    "submitter": [submitter.id, submitter.username, submitter.full_name],
    "reviewer": {
        reviewer1.id: [reviewer1.username, reviewer1.full_name, option1],
        reviewer2.id: [reviewer2.username, reviewer2.full_name, option2],
        ...
    },
    "media_id_list": [media1.id, media2.id, ...],
    "media_type_list": [media1.type, media2.type, ...],
    "documents_id_list": [document1.id, document2.id, ...],
    "document_type_list": [document1.type, document2.type, ...],
    "text": "text",
}
'''


class ReviewChoice:
    SFW = '0'
    NSFW = '1'
    REJECT = '2'
    REJECT_DUPLICATE = '3'
    QUERY = '4'
    WITHDRAW = '5'


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
            ]
        ]
    )

    submitter_id, submitter_username, submitter_fullname = submission_meta['submitter']
    await first_submission_message.reply_text(generate_submission_meta_string(submission_meta), reply_markup=inline_keyboard)


async def approve_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    action = query.data.split('.')[0]
    review_message = update.effective_message
    origin_message = review_message.reply_to_message

    reviewer_id, reviewer_username, reviewer_fullname = query.from_user.id, query.from_user.username, query.from_user.full_name
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text.split('submission_meta: ')[-1]))

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
            text=review_message.text.split('submission_meta: ')[0] + 'submission_meta: ' + base64.urlsafe_b64encode(pickle.dumps(submission_meta)).decode(), reply_markup=review_message.reply_markup)
        await query.answer(f"✅ 投票成功！{get_decision(submission_meta, reviewer_id)}")
        return
    # else if the submission has been approved by enough reviewers
    await query.answer("✅ 投票成功，此条投稿已通过")
    # then send this submission to the publish channel
    # if the submission is nsfw
    if ReviewChoice.NSFW in review_options:
        inline_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
            "跳到下一条", callback_data="skip")]])
        await context.bot.send_message(
            chat_id=TG_PUBLISH_CHANNEL, text="⚠️ #NSFW 提前预警", reply_markup=inline_keyboard)

    sent_messages = await send_submission(context=context, chat_id=TG_PUBLISH_CHANNEL, media_id_list=submission_meta['media_id_list'], media_type_list=submission_meta['media_type_list'], documents_id_list=submission_meta['documents_id_list'], document_type_list=submission_meta['document_type_list'], text=submission_meta['text'])
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta))


async def reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    review_message = update.effective_message
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text.split('submission_meta: ')[-1]))
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
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta))


async def reject_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    action = query.data.split('.')[0]
    review_message = update.effective_message

    reviewer_id, reviewer_username, reviewer_fullname = query.from_user.id, query.from_user.username, query.from_user.full_name
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text.split('submission_meta: ')[-1]))

    # if REJECT_DUPLICATE, only one reviewer is enough
    if action == ReviewChoice.REJECT_DUPLICATE:
        # if the reviewer has already approved or rejected the submission, remove the previous decision
        submission_meta, _ = remove_decision(submission_meta, reviewer_id)
        submission_meta['reviewer'][reviewer_id] = [
            reviewer_username, reviewer_fullname, action]
        await query.answer("✅ 投票成功，此条投稿已被拒绝")
        await review_message.edit_text(text=generate_submission_meta_string(submission_meta))
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
            text=review_message.text.split('submission_meta: ')[0] + 'submission_meta: ' + base64.urlsafe_b64encode(pickle.dumps(submission_meta)).decode(), reply_markup=review_message.reply_markup)
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
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta), reply_markup=InlineKeyboardMarkup(inline_keyboard_content))


async def send_custom_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
    review_message = update.message.reply_to_message
    # if there is not a submission_meta in the review_message
    if 'submission_meta: ' not in review_message.text:
        return
    submission_meta = pickle.loads(base64.urlsafe_b64decode(
        review_message.text.split('submission_meta: ')[-1]))
    # if the submission has not been rejected yet
    if get_submission_status(submission_meta)[0] not in [SubmissionStatus.REJECTED_NO_REASON, SubmissionStatus.REJECTED]:
        return
    # if the reviewer has not rejected the submission
    if update.message.from_user.id not in submission_meta['reviewer'] or submission_meta['reviewer'][update.message.from_user.id][2] in [ReviewChoice.SFW, ReviewChoice.NSFW]:
        await update.message.reply_text("😂 你没有投拒绝票")
        return
    # if the reason has not been changed
    if submission_meta['reviewer'][update.message.from_user.id][2] == update.message.text:
        return
    
    submission_meta['reviewer'][update.message.from_user.id][2] = update.message.text
    await review_message.edit_text(text=generate_submission_meta_string(submission_meta))

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
        review_message.text.split('submission_meta: ')[-1]))

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
        review_message.text.split('submission_meta: ')[-1]))

    submission_meta, removed = remove_decision(submission_meta, reviewer)
    if removed:
        await review_message.edit_text(text=review_message.text.split('submission_meta: ')[0] + 'submission_meta: ' + base64.urlsafe_b64encode(pickle.dumps(submission_meta)).decode(), reply_markup=review_message.reply_markup)
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
    elif ReviewChoice.REJECT_DUPLICATE in review_options:
        status = SubmissionStatus.REJECTED
        rejection_reason = "重复投稿"
    elif review_options.count(ReviewChoice.REJECT) >= REJECT_NUMBER_REQUIRED:
        status = SubmissionStatus.REJECTED_NO_REASON
    elif review_options.count(ReviewChoice.NSFW) + review_options.count(ReviewChoice.SFW) + review_options.count(ReviewChoice.REJECT) < len(review_options):
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
    submitter_id, submitter_username, submitter_fullname = submission_meta['submitter']
    submitter_string = f"Submitter: {submitter_fullname} ({f'@{submitter_username}, ' if submitter_username else ''}{submitter_id})\n"

    # reviewers_string
    reviewers_string = "Reviewers: "
    if status == SubmissionStatus.PENDING:
        reviewers_string += "在结果公布前暂时隐藏"
    else:
        for reviewer_id, [reviewer_username, reviewer_fullname, option] in submission_meta['reviewer'].items():
            option_text = ""
            match option:
                case ReviewChoice.SFW:
                    option_text = "🟢 Approved as SFW"
                case ReviewChoice.NSFW:
                    option_text = "🟡 Approved as NSFW"
                case ReviewChoice.REJECT:
                    option_text = "🔴 Rejected"
                case ReviewChoice.REJECT_DUPLICATE:
                    option_text = "🔴 Rejected as 重复投稿"
                case _:
                    option_text = f"🔴 Rejected as {get_rejection_reason_text(option)}"
            reviewers_string += f"\n- {option_text} by {reviewer_fullname} ({f'@{reviewer_username}, ' if reviewer_username else ''}{reviewer_id})"

    # status_string
    status_string = ""
    match status:
        case SubmissionStatus.PENDING:
            status_string = "Pending"
        case SubmissionStatus.APPROVED:
            status_string = "Approved as SFW" if ReviewChoice.NSFW not in review_options else "Approved as NSFW"
        case SubmissionStatus.REJECTED:
            status_string = f"Rejected as {rejection_reason}"
        case SubmissionStatus.REJECTED_NO_REASON:
            status_string = "Pending"

    # status_title
    status_title = "❔ A pending review submission" if status == SubmissionStatus.PENDING else (
        "✅ An approved submission" if status == SubmissionStatus.APPROVED else "❌ A rejected submission")
    submission_meta_text = f"submission_meta: {base64.urlsafe_b64encode(pickle.dumps(submission_meta)).decode()}" if status != SubmissionStatus.APPROVED else ""
    return dedent(f'''\
{status_title}

{submitter_string}
{reviewers_string}
Status: {status_string}{submission_meta_text}''')
