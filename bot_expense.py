# bot_expense.py
import os
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ========= CONFIG from env =========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Sheet1")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

CATEGORIES = os.environ.get("CATEGORIES", "Food,Household,Rent,Entertainment,Alco,Clothing,Cosmetics,Taxes,Meds,Travel").split(",")

# ========= Google Sheets client =========
def get_worksheet():
    if not GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON is not set")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(WORKSHEET_NAME)

# ========= Conversation states =========
AMOUNT, CATEGORY = range(2)

# ========= Helpers =========
def parse_amount(text: str):
    try:
        cleaned = text.replace(",", ".").strip()
        value = float(cleaned)
        return round(value, 2)
    except Exception:
        return None

def category_keyboard():
    buttons = [[InlineKeyboardButton(cat.strip(), callback_data=f"cat:{cat.strip()}")]
               for cat in CATEGORIES if cat.strip()]
    return InlineKeyboardMarkup(buttons)

async def write_row(amount: float, category: str, user) -> None:
    ws = get_worksheet()
    ts = datetime.now().isoformat(timespec="seconds")
    row = [
        ts,
        str(user.id),
        (user.username or "")[:64],
        amount,
        category
    ]
    # One-time: add headers manually in your sheet:
    # Timestamp | TelegramUserID | Username | Amount | Category
    ws.append_row(row, value_input_option="USER_ENTERED")

# ========= Handlers =========
async def start_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Type the sum:")
    return AMOUNT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = parse_amount(update.message.text)
    if amt is None or amt <= 0:
        await update.message.reply_text("Sum is not recognized, try to insert the numeric value, e.g. 12.50")
        return AMOUNT

    context.user_data["amount"] = amt
    await update.message.reply_text(
        f"Sum: {amt}. Now select the category:",
        reply_markup=category_keyboard()
    )
    return CATEGORY

async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if not data.startswith("cat:"):
        await query.edit_message_text("Choice invalid, please try again.")
        return CATEGORY

    category = data.split(":", 1)[1]
    amount = context.user_data.get("amount")
    if amount is None:
        await query.edit_message_text("Sum not found, please try again: /expense")
        return ConversationHandler.END

    try:
        await write_row(amount, category, query.from_user)
        await query.edit_message_text(f"✅ Recorded: {amount} — {category}")
    except Exception as e:
        await query.edit_message_text(f"⚠️ Recording failed: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("expense", start_expense)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            CATEGORY: [CallbackQueryHandler(category_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancel", cancel))
    return app

if __name__ == "__main__":
    # Optional: local run with long polling
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
