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
PORT = int(os.environ.get("PORT", "10000"))

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
    global app_telegram
    app_telegram = build_application()

    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    if base_url:
        url = base_url + WEBHOOK_PATH
        await app_telegram.bot.set_webhook(url=url)
        logger.info("Webhook set to %s", url)
    else:
        logger.warning("BASE_URL is not set. Set it in Render env and redeploy to activate webhook.")

routes = [
    Route("/", root, methods=["GET"]),
    Route(WEBHOOK_PATH, telegram_webhook, methods=["POST"]),
]

app = Starlette(routes=routes, on_startup=[startup])
