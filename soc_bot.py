import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import signal

from fastapi import FastAPI
import uvicorn

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== Config & Paths ======================

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_FILE = DATA_DIR / "admins.json"

def load_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v else default

BOT_TOKEN = load_env("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required")

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
    print(f"[DEBUG] Added admin: {chat_id} ({username})")
    return True

def remove_admin(chat_id: int) -> bool:
    admins = read_admins()
    n = len(admins)
    admins = [a for a in admins if a["chat_id"] != chat_id]
    if len(admins) == n:
        return False
    write_admins(admins)
    print(f"[DEBUG] Removed admin: {chat_id}")
    return True

def list_admin_chat_ids() -> List[int]:
    return [a["chat_id"] for a in read_admins()]

# ================= Helpers =================

def escape_md(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

# ================= Telegram handlers =====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    chat = update.effective_chat
    if not chat:
        return
    added = add_admin(chat.id, user.username if user else None)
    await update.message.reply_text(
        "✅ Registered. You will now receive SOC alerts here." if added else
        "⚡ You are already registered to receive SOC alerts here."
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return
    removed = remove_admin(chat.id)
    await update.message.reply_text(
        "🛑 Removed. You will no longer receive SOC alerts here." if removed else
        "ℹ️ You were not registered."
    )

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    admins = read_admins()
    if not admins:
        await update.message.reply_text("No admins registered yet.")
        return
    lines = [f"• {a.get('username') or 'unknown'} — `{a['chat_id']}`" for a in admins]
    txt = "👥 *Registered Admins:*\n" + "\n".join(lines)
    await update.message.reply_text(escape_md(txt), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if chat.id not in list_admin_chat_ids():
        await update.message.reply_text("❌ Only registered admins can broadcast alerts.")
        return
    text = "🔥 *Test Alert from SOC Bot*"
    targets = list_admin_chat_ids()
    if not targets:
        await update.message.reply_text("No recipients registered yet.")
        return
    for cid in targets:
        try:
            await context.bot.send_message(chat_id=cid, text=escape_md(text), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
    await update.message.reply_text("✅ Test alert broadcasted.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    help_text = (
        "🛡️ *SOC Bot Commands:*\n\n"
        "/start - Register yourself to receive SOC alerts.\n"
        "/stop - Unregister from receiving SOC alerts.\n"
        "/admins - List all registered admins.\n"
        "/testalert - Send a test alert to all registered admins (admins only).\n"
        "/help - Show this help message.\n"
    )
    await update.message.reply_text(escape_md(help_text), parse_mode=ParseMode.MARKDOWN_V2)

# ================= FastAPI for health check ==================

api = FastAPI(title="SOC Bot Health Check")

@api.get("/health")
async def health():
    return {"ok": True}

# ===================== Main ==============================

async def main():
    tg_app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("stop", cmd_stop))
    tg_app.add_handler(CommandHandler("admins", cmd_admins))
    tg_app.add_handler(CommandHandler("testalert", cmd_testalert))
    tg_app.add_handler(CommandHandler("help", cmd_help))

    print(f"[DEBUG] SUPER_ADMIN_IDS: {SUPER_ADMIN_IDS}")
    print(f"[DEBUG] Current admins: {list_admin_chat_ids()}")

    await tg_app.initialize()
    await tg_app.run_polling(drop_pending_updates=True)

    async def run_uvicorn():
        config = uvicorn.Config(api, host="0.0.0.0", port=8080, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    # Run FastAPI alongside Telegram bot
    await asyncio.gather(run_uvicorn(), asyncio.Event().wait())

if __name__ == "__main__":
    asyncio.run(main())
