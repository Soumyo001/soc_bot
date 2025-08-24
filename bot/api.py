from fastapi import FastAPI, Request, HTTPException, Header
from config import BOT_TOKEN, API_KEY
from helpers.formatter import format_alert
from storage import get_receiving_admins
from telegram import Update, Bot
from telegram.constants import ParseMode

api = FastAPI(title="SOC Bot Ingest API")

@api.get("/health")
async def health():
    return {"ok": True}

# Accepts JSON POSTs from Wazuh/TheHive/custom scripts
@api.post("/v1/ingest")
async def ingest(request: Request, x_api_key: str = Header(None)):
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

    receiving = get_receiving_admins()
    if not receiving:
        return {"accepted": True, "forwarded": False, "reason": "no_admins_in_receive_mode"}

    bot = Bot(BOT_TOKEN)
    text = format_alert(summary, severity, details, tags if isinstance(tags, list) else None)

    results = []
    for cid in receiving:
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            results.append({"chat_id": cid, "status": "sent"})
        except Exception as e:
            results.append({"chat_id": cid, "status": "error", "error": str(e)})

    return {"accepted": True, "forwarded": True, "results": results}