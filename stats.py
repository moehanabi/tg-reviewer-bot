from textwrap import dedent

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from db_op import Reviewer, Submitter
from env import TG_REVIEWER_GROUP

import re

async def submitter_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        if not str(update.effective_chat.id).startswith("-100"):
            submitter_id = str(update.effective_chat.id)
        elif str(update.effective_chat.id) == TG_REVIEWER_GROUP:
            if update.message.reply_to_message:
                replyto_user_id = str(update.message.reply_to_message.from_user.id)
                self_id = str((await context.bot.get_me()).id)
                if replyto_user_id == self_id:
                    tag_submitter_id = re.findall(r"#SUBMITTER_(\d+)", update.message.reply_to_message.text)
                    if tag_submitter_id:
                        submitter_id = tag_submitter_id[-1]
                    else:
                        update.message.reply_text("请提供用户ID")
                        return
                else:
                    submitter_id = replyto_user_id
            else:
                submitter_id = str(update.effective_user.id)
        else:
            return
    else:
        if str(update.effective_chat.id) == TG_REVIEWER_GROUP:
            submitter_id = context.args[0]
        else:
            return
    if submitter_id.startswith(("#USER_","#SUBMITTER_")):
        if submitter_id.startswith("#USER_"):
            submitter_id = submitter_id[6:]
        elif submitter_id.startswith("#SUBMITTER_"):
            submitter_id = submitter_id[11:]
    if not submitter_id.isdigit():
        await update.message.reply_text(
            f"ID `{escape_markdown(submitter_id,version=2,)}` 无效",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    submitter_info = Submitter.get_submitter(submitter_id)
    if not submitter_info or not submitter_info.submission_count:
        await update.message.reply_text("还没有投稿过任何内容")
        return
    reply_string = "*\\=\\= 基础信息 \\=\\=*\n" + escape_markdown(
        f"投稿数量: {submitter_info.submission_count}\n通过数量: {submitter_info.approved_count}\n拒绝数量: {submitter_info.rejected_count}\n投稿通过率: {submitter_info.approved_count / (submitter_info.rejected_count + submitter_info.approved_count) * 100:.2f}%\n\n#USER_{submitter_id} #SUBMITTER_{submitter_id}",
        version=2,
    )
    await update.message.reply_text(
        reply_string, parse_mode=ParseMode.MARKDOWN_V2
    )


async def reviewer_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        if not str(update.effective_chat.id).startswith("-100"):
            reviewer_id = str(update.effective_chat.id)
        elif str(update.effective_chat.id) == TG_REVIEWER_GROUP:
            reviewer_id = str(update.effective_user.id)
        else:
            return
    elif str(update.effective_chat.id) == TG_REVIEWER_GROUP:
        reviewer_id = context.args[0]
    else:
        return
    if reviewer_id.startswith("#REVIEWER_"):
        reviewer_id = reviewer_id[10:]
    if not reviewer_id.isdigit():
        await update.message.reply_text(
            f"ID `{escape_markdown(reviewer_id,version=2,)}` 无效",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    reviewer_info = Reviewer.get_reviewer(reviewer_id)
    if not reviewer_info:
        await update.message.reply_text("还没有审核过任何内容")
        return
    reply_string = "*\\=\\= 基础信息 \\=\\=*\n" + escape_markdown(
        dedent(
            f"""
        审核数量: {reviewer_info.approve_count + reviewer_info.reject_count}
        通过数量: {reviewer_info.approve_count}
        拒稿数量: {reviewer_info.reject_count}
        通过但稿件被拒数量: {reviewer_info.approve_but_rejected_count}
        拒稿但稿件通过数量: {reviewer_info.reject_but_approved_count}
        
        通过但稿件被拒数量 / 通过数量: {reviewer_info.approve_but_rejected_count / reviewer_info.approve_count * 100 if reviewer_info.approve_count else 0.0:.2f}%
        拒稿但稿件通过数量 / 拒稿数量: {reviewer_info.reject_but_approved_count / reviewer_info.reject_count * 100 if reviewer_info.reject_count else 0.0:.2f}%
        
        最后一次审核时间: {reviewer_info.last_time}
        
        #REVIEWER_{reviewer_id}"""
        ),
        version=2,
    )
    await update.message.reply_text(
        reply_string, parse_mode=ParseMode.MARKDOWN_V2
    )
