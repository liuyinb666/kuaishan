import os
import random
from telegram import Update
from telegram.ext import Application, CommandHandler

TOKEN = os.environ.get("BOT_TOKEN")

async def dice(update: Update, context):
    args = context.args
    
    # /dice show 3  -> 强制显示3点
    if args and args[0] == "show" and len(args) == 2:
        try:
            num = int(args[1])
            if 1 <= num <= 6:
                await update.message.bot.send_dice(update.message.chat_id, emoji="🎲", value=num)
                return
        except:
            pass
    
    # 普通随机
    num = random.randint(1, 6)
    await update.message.bot.send_dice(update.message.chat_id, emoji="🎲", value=num)

async def roll(update: Update, context):
    text = " ".join(context.args) if context.args else ""
    
    # 支持 3d6 或 1-100
    import re
    m = re.match(r'(\d+)d(\d+)', text)
    if m:
        c, s = int(m[1]), int(m[2])
        r = [random.randint(1, s) for _ in range(min(c, 50))]
        await update.message.reply_text(f"🎲 {c}d{s}: {r} = {sum(r)}")
        return
    
    m = re.match(r'(\d+)-(\d+)', text)
    if m:
        lo, hi = int(m[1]), int(m[2])
        await update.message.reply_text(f"🎲 {lo}-{hi}: {random.randint(lo, hi)}")
        return

async def start(update: Update, context):
    await update.message.reply_text("指令:\n/dice show 3\n/roll 3d6\n/roll 1-100")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("roll", roll))
    app.run_polling()

if __name__ == "__main__":
    main()