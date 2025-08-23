from telegram import Bot
from telegram.constants import ParseMode
import asyncio

BOT_TOKEN = "8348084001:AAFpXhnwKoKxKwkkMrd46kRzA-rupGAaOp0"
CHAT_ID = 5522743536  # replace with actual chat id from step 1

bot = Bot(BOT_TOKEN)

async def main():
    await bot.send_message(chat_id=CHAT_ID, text="Hello\\! Test message", parse_mode=ParseMode.MARKDOWN_V2)

asyncio.run(main())