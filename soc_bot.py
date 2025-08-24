import asyncio
import signal
import uvicorn
from telegram.ext import Application, CommandHandler
from bot.config import BOT_TOKEN
from bot.bot import cmd_admins, cmd_broadcast, cmd_help, cmd_receive_alert, cmd_show_state, cmd_start, cmd_stop, cmd_stop_receive, cmd_testalert
from bot.storage import list_admin_chat_ids
from bot.api import api


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
