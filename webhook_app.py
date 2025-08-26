# webhook_app.py
import os
import logging
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.routing import Route
from telegram import Update

from bot_expense import build_application, BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

WEBHOOK_PATH = f"/telegram/{BOT_TOKEN}" if BOT_TOKEN else "/telegram/secret"

app_telegram = None

async def root(_request):
    return PlainTextResponse("OK")

async def telegram_webhook(request):
    global app_telegram
    if app_telegram is None:
        return JSONResponse({"error": "Bot not ready"}, status_code=503)
    data = await request.json()
    update = Update.de_json(data, app_telegram.bot)
    await app_telegram.process_update(update)
    return PlainTextResponse("ok")

async def startup():
    """Called by Starlette when the server starts."""
    global app_telegram
    app_telegram = build_application()

    # 🔴 ВАЖНО: сначала initialize, потом (опционально) set_webhook, затем start
    await app_telegram.initialize()

    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    if base_url:
        url = base_url + WEBHOOK_PATH
        await app_telegram.bot.set_webhook(url=url)
        logger.info("Webhook set to %s", url)
    else:
        logger.warning("BASE_URL is not set. Set it in Render env and redeploy to activate webhook.")

    await app_telegram.start()

async def shutdown():
    """Graceful stop on server shutdown/redeploy."""
    global app_telegram
    if app_telegram:
        await app_telegram.stop()
        await app_telegram.shutdown()

routes = [
    Route("/", root, methods=["GET"]),
    Route(WEBHOOK_PATH, telegram_webhook, methods=["POST"]),
]

app = Starlette(routes=routes, on_startup=[startup], on_shutdown=[shutdown])
]

app = Starlette(routes=routes, on_startup=[startup], on_shutdown=[shutdown])
