import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import signal

from fastapi import FastAPI, Request, HTTPException, Header
import uvicorn

from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== Config & Paths ======================

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_FILE = DATA_DIR / "admins.json"
RECEIVE_MODE_FILE = DATA_DIR / "receive_mode.json"

def load_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v else default

BOT_TOKEN = load_env("BOT_TOKEN")
API_KEY = load_env("API_KEY")  # for ingest authentication

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required (from BotFather). Put it in environment variables")

# ----------------- Admin JSON helpers -----------------

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
    return write_admins(new_admins)

def list_admin_chat_ids() -> List[int]:
    return [a["chat_id"] for a in read_admins()]

# ----------------- Receive-mode helpers -----------------
def set_receive_mode(enabled: bool) -> None:
    tmp = RECEIVE_MODE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"enabled": bool(enabled)}, f)
    tmp.replace(RECEIVE_MODE_FILE)

def get_receive_mode() -> bool:
    if not RECEIVE_MODE_FILE.exists():
        return False
    try:
        with RECEIVE_MODE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return bool(data.get("enabled", False))
    except Exception:
        return False

# ----------------- Formatting helpers -----------------
def escape_md_fragment(text: str) -> str:
    """Escape for MarkdownV2, for dynamic fragments only (NOT whole message)."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def format_alert(summary: str, severity: int,
                 details: Optional[Dict[str, Any]] = None,
                 tags: Optional[List[str]] = None) -> str:
    sev = max(0, min(10, int(severity or 5)))
    icons = ["🟢","🟢","🟢","🟡","🟡","🟡","🟠","🟠","🔴","🔴","🔥"]
    # Escape only user-provided fields
    t = f"{icons[sev]} {escape_md_fragment(f"*{str(summary)}*")}"
    if tags:
        safe_tags = " ".join(f"{escape_md_fragment(f"#{str(x)}")}" for x in tags)
        t += f" \n{safe_tags}"
    if details is not None:
        pretty = json.dumps(details, indent=2, ensure_ascii=False)
        # Put raw JSON inside code block so we don't need to escape inside
        t += f"\n*Details:*\n```json\n{pretty}\n```"
    return t

# ----------------- Telegram handlers (bot) -----------------a

def _is_admin(chat_id: int) -> bool:
    return chat_id in set(list_admin_chat_ids())

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return
    added = add_admin(chat.id, user.username if user else None)
    if added:
        await update.message.reply_text(f"✅ Registered user: {user.username}")
        await cmd_help(update=update, context=context)
    else:
        await update.message.reply_text("ℹ️ Already registered.")
        

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return
    removed = remove_admin(chat.id)
    await update.message.reply_text("🛑 Removed." if removed else "ℹ️ You were not registered.")

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    admins = read_admins()
    if not admins:
        await update.message.reply_text("No admins registered yet.")
        return
    lines = []
    for a in admins:
        uname = escape_md_fragment(a.get("username") or "unknown")
        lines.append(f"• {uname} — `{a['chat_id']}`")
    txt = "👥 *Registered Admins:*\n" + "\n".join(lines)
    # Do NOT escape the whole message; only fragments were escaped above
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_receive_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Enable continuous ingestion
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return
    if not _is_admin(chat.id):
        await update.message.reply_text("❌ Only registered admins can enable receive mode.")
        return
    if get_receive_mode() == True:
        await update.message.reply_text("⚠️ Receive mode already ENABLED. ")
        return
    set_receive_mode(True)
    await update.message.reply_text("✅ Receive mode ENABLED. Incoming suspicious alerts will be forwarded to admins.")

async def cmd_stop_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Disable continuous ingestion
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return
    if not _is_admin(chat.id):
        await update.message.reply_text("❌ Only registered admins can disable receive mode.")
        return
    if get_receive_mode() == False:
        await update.message.reply_text("⚠️ Receive mode already DISABLED. ")
        return
    set_receive_mode(False)
    await update.message.reply_text("🛑 Receive mode DISABLED. Incoming alerts will NOT be forwarded.")

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = format_alert("Test alert from SOC Bot", 6, {"demo": True}, ["TEST"])
    for cid in list_admin_chat_ids():
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
    await update.message.reply_text("✅ Test alert sent to all admins.")

async def cmd_show_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    mode = get_receive_mode()
    admins = read_admins()
    # Only escape dynamic parts if needed; here it's static text + numbers.
    state = f"📊 *Current State:*\n\nReceive mode: {'✅ ON' if mode else '❌ OFF'}\nAdmins: {len(admins)}"
    await update.message.reply_text(state, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return

    admins = list_admin_chat_ids()
    if chat.id not in admins:
        await update.message.reply_text("❌ Only registered admins can broadcast.")
        return
    parts = (update.message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("⚠️ Usage: /broadcast <message>")
        return
    body = escape_md_fragment(parts[1].strip())
    for cid in admins:
        try:
            if cid == chat.id:
                continue
            await context.bot.send_message(chat_id=cid, text=body, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
    await update.message.reply_text("✅ Broadcast sent.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    help_text = (
        "🛡️ *SOC Bot Commands:*\n\n"
        "/start - Register yourself to receive SOC alerts.\n"
        "/stop - Unregister from receiving SOC alerts.\n"
        "/admins - List all registered admins.\n"
        "/receive_alert - ENABLE continuous forwarding of suspicious alerts (admins only).\n"
        "/stop_receive - DISABLE continuous forwarding of suspicious alerts.\n"
        "/testalert - Send a test alert to all admins.\n"
        "/broadcast <msg> - Send a custom message to all admins (admins only).\n"
        "/show_state - Show receive mode and admin count.\n"
        "/help - Show this message.\n"
    )
    # Static content — safe to send as-is with MarkdownV2
    await update.message.reply_text(escape_md_fragment(help_text), parse_mode=ParseMode.MARKDOWN_V2)

# ----------------- FastAPI app (runs in separate process) -----------------
api = FastAPI(title="SOC Bot Ingest API")

@api.get("/health")
async def health():
    return {"ok": True}

# Accepts JSON POSTs from Wazuh/TheHive/custom scripts
@api.post("/v1/ingest")
async def ingest(request: Request, x_api_key: str = Header(None)):
    # AuthN: only trusted systems with the shared API key
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(403, "Forbidden: invalid API key")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    summary = payload.get("summary", "Alert")
    severity = payload.get("severity", 5)
    details = payload.get("details")
    tags = payload.get("tags")

    if not get_receive_mode():
        return {"accepted": True, "forwarded": False, "reason": "receive_mode_disabled"}

    bot = Bot(BOT_TOKEN)
    text = format_alert(summary, severity, details, tags if isinstance(tags, list) else None)

    results = []
    for cid in list_admin_chat_ids():
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            results.append({"chat_id": cid, "status": "sent"})
        except Exception as e:
            results.append({"chat_id": cid, "status": "error", "error": str(e)})

    return {"accepted": True, "forwarded": True, "results": results}

# ===================== Main ==============================
async def main():
    tg_app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("stop", cmd_stop))
    tg_app.add_handler(CommandHandler("admins", cmd_admins))
    tg_app.add_handler(CommandHandler("receive_alert", cmd_receive_alert))
    tg_app.add_handler(CommandHandler("stop_receive", cmd_stop_receive))
    tg_app.add_handler(CommandHandler("show_state", cmd_show_state))
    tg_app.add_handler(CommandHandler("testalert", cmd_testalert))
    tg_app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    tg_app.add_handler(CommandHandler("help", cmd_help))

    print(f"[DEBUG] Current admins: {list_admin_chat_ids()}")

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)

    async def run_uvicorn():
        config = uvicorn.Config(api, host="0.0.0.0", port=8080, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    await asyncio.gather(run_uvicorn(), asyncio.Event().wait())

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
