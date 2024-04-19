from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from db_op import Submitter
from utils import TG_REVIEWER_GROUP


async def submitter_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    userid = update.effective_user.id
    if str(update.effective_chat.id) == TG_REVIEWER_GROUP:
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
