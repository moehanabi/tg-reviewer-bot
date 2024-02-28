from telegram import Update
from telegram.ext import ContextTypes


async def handle_new_sumission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="请开始你的投稿"
    )
    
