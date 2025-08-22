import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import signal
import platform

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== Config & Paths ======================

DATA_DIR = Path("data")       # centralized admins.json inside repo/container
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_FILE = DATA_DIR / "admins.json"

def load_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip()

BOT_TOKEN = load_env("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required (from BotFather). Put it in environment variables")

SUPER_ADMIN_IDS = {int(x) for x in (load_env("SUPER_ADMIN_IDS", "") or "").split(",") if x.strip()}

# =================== Admin storage ========================

def read_admins() -> List[Dict[str, Any]]:
    if not ADMIN_FILE.exists():
        return []
    try:
        with ADMIN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("admins", [])
    except Exception:
        return []

def write_admins(admins: List[Dict[str, Any]]) -> None:
    tmp = ADMIN_FILE.with_suffix(".json.tmp")
    json.dump({"admins": admins}, tmp.open("w", encoding="utf-8"), indent=2)
    tmp.replace(ADMIN_FILE)

def add_admin(chat_id: int, username: Optional[str]) -> bool:
    admins = read_admins()
    if any(a["chat_id"] == chat_id for a in admins):
        return False
    admins.append({"chat_id": chat_id, "username": username})
    write_admins(admins)
    return True

def remove_admin(chat_id: int) -> bool:
    admins = read_admins()
    n = len(admins)
    admins = [a for a in admins if a["chat_id"] != chat_id]
    if len(admins) == n:
        return False
    write_admins(admins)
    return True

def list_admin_chat_ids() -> List[int]:
    return [a["chat_id"] for a in read_admins()]

# ================= Telegram handlers =====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat is None:
        return
    added = add_admin(chat.id, user.username if user else None)
    if added:
        await update.message.reply_text("✅ Registered. You will now receive SOC alerts here.")
    else:
        await update.message.reply_text("⚡ You are already registered to receive SOC alerts here.")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None:
        return
    removed = remove_admin(chat.id)
    if removed:
        await update.message.reply_text("🛑 Removed. You will no longer receive SOC alerts here.")
    else:
        await update.message.reply_text("ℹ️ You were not registered.")

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Admin-only command.")
        return
    admins = read_admins()
    if not admins:
        await update.message.reply_text("No admins registered yet.")
        return
    lines = [f"• {a.get('username') or 'unknown'} — `{a['chat_id']}`" for a in admins]
    txt = "👥 *Registered Admins:*\n" + "\n".join(lines)
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Admin-only command.")
        return
    text = "🔥 *Test Alert from SOC Bot*"
    targets = list_admin_chat_ids()
    if not targets:
        await update.message.reply_text("No recipients registered yet.")
        return
    for cid in targets:
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
    await update.message.reply_text("✅ Test alert broadcasted.")

# ===================== Main ==============================

async def main():
    tg_app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("stop", cmd_stop))
    tg_app.add_handler(CommandHandler("admins", cmd_admins))
    tg_app.add_handler(CommandHandler("testalert", cmd_testalert))
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()  # Keep running

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, loop.stop)
        except NotImplementedError:
            pass
    try:
        loop.run_until_complete(main())
    finally:
        pending = asyncio.all_tasks(loop)
        for t in pending:
            t.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()
