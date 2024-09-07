from textwrap import dedent

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from src.config import ReviewConfig
from src.database.db_op import Reviewer, Submitter


async def submitter_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    userid = update.effective_user.id
    if str(update.effective_chat.id) == ReviewConfig.REVIEWER_GROUP:
        if not context.args:
            await update.message.reply_text("请提供用户ID")
            return
        userid = context.args[0]
    submitter_info = Submitter.get_submitter(userid)
    if not submitter_info or not submitter_info.submission_count:
        await update.message.reply_text("还没有投稿过任何内容")
        return
    reply_string = "*\-\-基础信息\-\-*\n" + escape_markdown(
        f"投稿数量: {submitter_info.submission_count}\n通过数量: {submitter_info.approved_count}\n拒绝数量: {submitter_info.rejected_count}\n投稿通过率: {submitter_info.approved_count / submitter_info.submission_count * 100:.2f}%",
        version=2,
    )
    await update.message.reply_text(
        reply_string, parse_mode=ParseMode.MARKDOWN_V2
    )


async def reviewer_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("请提供审稿人 ID")
        return
    reviewer_id = context.args[0]
    reviewer_info = Reviewer.get_reviewer(reviewer_id)
    if not reviewer_info:
        await update.message.reply_text("还没有审核过任何内容")
        return
    reply_string = "*\-\-基础信息\-\-*\n" + escape_markdown(
        dedent(
            f"""
        审核数量: {reviewer_info.approve_count + reviewer_info.reject_count}
        通过数量: {reviewer_info.approve_count}
        拒稿数量: {reviewer_info.reject_count}
        通过但稿件被拒数量: {reviewer_info.approve_but_rejected_count}
        拒稿但稿件通过数量: {reviewer_info.reject_but_approved_count}
        
        通过但稿件被拒数量 / 通过数量: {reviewer_info.approve_but_rejected_count / reviewer_info.approve_count * 100 if reviewer_info.approve_count else 0.0:.2f}%
        拒稿但稿件通过数量 / 拒稿数量: {reviewer_info.reject_but_approved_count / reviewer_info.reject_count * 100 if reviewer_info.reject_count else 0.0:.2f}%
        
        最后一次审核时间: {reviewer_info.last_time}"""
        ),
        version=2,
    )
    await update.message.reply_text(
        reply_string, parse_mode=ParseMode.MARKDOWN_V2
    )
