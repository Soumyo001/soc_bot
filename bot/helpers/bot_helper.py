from bot.storage import get_receiving_admins, write_admins, list_admin_chat_ids, read_admins
from telegram import Update
from telegram.ext import ContextTypes


def _is_admin(chat_id: int) -> bool:
    return chat_id in set(list_admin_chat_ids())

def get_receive_mode(chat_id: int) -> bool:
    return chat_id in get_receiving_admins()

def set_admin_receive(chat_id: int, enabled: bool) -> bool:
    admins = read_admins()
    changed = False
    for a in admins:
        if a["chat_id"] == chat_id:
            a["receive"] = enabled
            changed = True
    if changed:
        write_admins(admins)
    return changed

async def toggle_receive(update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool):
    if not update.message:
        return
    chat = update.effective_chat
    if not chat or not _is_admin(chat.id):
        await update.message.reply_text(f"❌ Only registered admins can {"enable" if enable else "disable"} receive mode.")
        return
    if get_receive_mode(chat.id) == enable:
        await update.message.reply_text(f"⚠️ Receive mode already {"ENABLED" if enable else "DISABLED"}.")
        return
    set_admin_receive(chat.id, enable)
    await update.message.reply_text(
        "✅ You will now receive incoming suspicious alerts.\nUse /stop_receive to disable." if enable else "🛑 You will no longer receive alerts."
    )