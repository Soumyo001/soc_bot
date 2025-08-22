import asyncio
import json
import os
import platform
import signal
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ================= Config & Paths =================

def data_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SOC_BOT"
    elif system == "linux":
        return Path("/var/lib/soc_bot")
    elif system == "darwin":
        return Path("/Library/Application Support/SOC_BOT")
    else:
        return Path(os.environ.get("HOME", str(Path.cwd()))) / ".soc_bot"

DATA_DIR = data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_FILE = DATA_DIR / "admins.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN is required (from BotFather).")

SUPER_ADMIN_IDS = {
    int(x) for x in (os.environ.get("SUPER_ADMIN_IDS", "") or "").split(",") if x.strip()
}

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

# ================= Admin Store =================

def read_admins() -> List[Dict[str, Any]]:
    if not ADMIN_FILE.exists():
        return []
    try:
        with ADMIN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("admins", []) if isinstance(data, dict) else []
    except Exception:
        return []

def write_admins(admins: List[Dict[str, Any]]) -> None:
    tmp = ADMIN_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"admins": admins}, f, indent=2)
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
    new_admins = [a for a in admins if a["chat_id"] != chat_id]
    if len(new_admins) == len(admins):
        return False
    write_admins(new_admins)
    return True

def list_admin_chat_ids() -> List[int]:
    return [a["chat_id"] for a in read_admins()]

# ================= Helpers =================

def severity_icon(sev: int) -> str:
    sev = max(0, min(10, int(sev)))
    return ["🟢","🟢","🟢","🟡","🟡","🟡","🟠","🟠","🔴","🔴","🔥"][sev]

def escape_md(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def format_alert(summary: str, severity: int, details: Optional[Dict[str, Any]]=None, tags: Optional[List[str]]=None) -> str:
    t = f"{severity_icon(severity)} *{escape_md(summary)}*"
    if tags:
        t += " " + " ".join(f"#{escape_md(x)}" for x in tags)
    if details:
        pretty = json.dumps(details, indent=2, ensure_ascii=False)
        t += f"\n*Details:*\n```\n{pretty}\n```"
    return t

# ================= FastAPI =================

class IngestBody(BaseModel):
    summary: str
    severity: int = Field(5, ge=0, le=10)
    details: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

api = FastAPI(title="SOC Bot Ingest API")
tg_app: Optional[Application] = None

@api.get("/health")
async def health():
    return {"ok": True}

@api.post("/v1/ingest")
async def ingest(item: IngestBody, request: Request):
    global tg_app
    if tg_app is None:
        raise HTTPException(503, "Telegram bot not initialized")

    text = format_alert(item.summary, item.severity, item.details, item.tags)
    targets = list_admin_chat_ids()
    if not targets:
        raise HTTPException(400, "No admins registered")

    async def send_one(cid: int):
        try:
            await tg_app.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            return {"chat_id": cid, "status": "sent"}
        except Exception as e:
            return {"chat_id": cid, "status": "error", "error": str(e)}

    results = await asyncio.gather(*(send_one(cid) for cid in targets))
    return {"results": results}

# ================= Telegram Commands =================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.effective_chat:
        return
    added = add_admin(update.effective_chat.id, user.username if user else None)
    await update.message.reply_text("✅ Registered." if added else "ℹ️ Already registered.")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    removed = remove_admin(update.effective_chat.id)
    await update.message.reply_text("🛑 Removed." if removed else "ℹ️ Not registered.")

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Admin-only command.")
        return
    admins = read_admins()
    if not admins:
        await update.message.reply_text("No admins yet.")
        return
    lines = [f"• {a.get('username') or 'unknown'} — `{a['chat_id']}`" for a in admins]
    await update.message.reply_text("👥 *Admins:*\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Admin-only command.")
        return
    text = format_alert("Test Alert", 6, {"demo": True}, ["TEST"])
    for cid in list_admin_chat_ids():
        await context.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Test alert sent.")

# ================= Bootstrap =================

async def run_uvicorn():
    config = uvicorn.Config(api, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    global tg_app
    tg_app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("stop", cmd_stop))
    tg_app.add_handler(CommandHandler("admins", cmd_admins))
    tg_app.add_handler(CommandHandler("testalert", cmd_testalert))

    async def run_polling():
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

    await asyncio.gather(run_polling(), run_uvicorn())

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
        loop.close()
