from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from .storage import add_admin, remove_admin, list_admin_chat_ids, read_admins
from .helpers.formatter import escape_md_fragment, format_alert
from .helpers.bot_helper import toggle_receive



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
    await toggle_receive(update, context, True)

async def cmd_stop_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await toggle_receive(update, context, False)

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if not chat:
        return
    admins = list_admin_chat_ids()
    if chat.id not in admins:
        await update.message.reply_text("❌ Only registered admins can send alert.")
        return
    text = format_alert("Test alert from SOC Bot", 6, {"demo": True}, ["TEST"])
    for cid in admins:
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
    await update.message.reply_text("✅ Test alert sent to all admins.")

async def cmd_show_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    admins = read_admins()
    lines = []
    for a in admins:
        uname = escape_md_fragment(a.get("username") or "unknown")
        status = "✅ ON" if a.get("receive", False) else "❌ OFF"
        lines.append(f"• {uname} — `{a['chat_id']}` — {status}")
    txt = "📊 *Current State:*\n\n" + "\n".join(lines)
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN_V2)

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