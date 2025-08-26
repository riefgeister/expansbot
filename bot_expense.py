import os, json, pathlib, logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("expense-bot")

# ---------- CONFIG (set BOT_TOKEN & SPREADSHEET_ID in Run config) ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Sheet1")
GOOGLE_CREDENTIALS_JSON_FILE = os.environ.get("GOOGLE_CREDENTIALS_JSON_FILE", "").strip()
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
# Button categories (edit as you like)
CATEGORIES = [
    "Food", "Household", "Rent", "Entertainment", "Alco",
    "Clothing", "Cosmetics", "Taxes", "Meds", "Travel"
]

# ---------- GOOGLE SHEETS ----------
def _load_service_account_info() -> dict:
    path = pathlib.Path(GOOGLE_CREDENTIALS_JSON_FILE)
    if not path.exists():
        raise RuntimeError(f"Google credentials file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def get_worksheet():
    if not SPREADSHEET_ID:
        raise RuntimeError("SPREADSHEET_ID is not set")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = _load_service_account_info()
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(WORKSHEET_NAME or "Sheet1")

# ---------- HELPERS ----------
def parse_amount(text: str):
    try:
        return round(float(text.replace(",", ".").strip()), 2)
    except Exception:
        return None

def category_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(c, callback_data=f"cat:{c}")] for c in CATEGORIES]
    )

def local_tz():
    # no tzdata dependency: use OS tz or UTC
    return (datetime.now().astimezone().tzinfo) or timezone.utc

def period_start(period: str, now: datetime) -> datetime:
    p = (period or "").lower()
    if p == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "week":
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def parse_ts(ts_str: str, tz) -> datetime | None:
    try:
        s = (ts_str or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except Exception:
        return None

# ---------- COMMANDS ----------
async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I record expenses to Google Sheets.\n\n"
        "Commands:\n"
        "• /expense — add an expense\n"
        "• /stats [today|week|month] [all] — totals\n"
        "• /cancel — cancel input"
    )

async def cmd_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # start flow (no ConversationHandler needed)
    context.user_data.clear()
    context.user_data["await"] = "amount"
    await update.message.reply_text("Enter amount (e.g., 12.50):")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle amount step if we're awaiting it
    if context.user_data.get("await") != "amount":
        return
    amt = parse_amount(update.message.text)
    if amt is None or amt <= 0:
        await update.message.reply_text("Not a number. Try again, e.g., 12.50")
        return
    context.user_data["amount"] = amt
    context.user_data["await"] = "category"
    await update.message.reply_text("Pick a category:", reply_markup=category_keyboard())

async def on_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if context.user_data.get("await") != "category":
        await query.edit_message_text("No pending expense. Start again with /expense")
        return
    data = query.data or ""
    if not data.startswith("cat:"):
        await query.edit_message_text("Invalid choice. Try again.")
        return

    category = data.split(":", 1)[1]
    amount = context.user_data.get("amount")
    if amount is None:
        await query.edit_message_text("Amount missing. Start again: /expense")
        context.user_data.clear()
        return

    try:
        ws = get_worksheet()
        ts = datetime.now(local_tz()).isoformat(timespec="seconds")
        row = [ts, str(query.from_user.id), (query.from_user.username or "")[:64], amount, category]
        # Add this header once in your sheet if you want:
        # Timestamp | TelegramUserID | Username | Amount | Category
        ws.append_row(row, value_input_option="USER_ENTERED")
        await query.edit_message_text(f"✅ Recorded: {amount} — {category}")
    except Exception as e:
        log.exception("Write failed")
        await query.edit_message_text(f"⚠️ Failed to write: {e}")

    context.user_data.clear()

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stats [today|week|month] [all]
    """
    args = [a.lower() for a in (context.args or [])]
    period = next((a for a in args if a in ("today", "week", "month")), "month")
    include_all = ("all" in args)

    tz = local_tz()
    now = datetime.now(tz)
    start_dt = period_start(period, now)

    try:
        ws = get_worksheet()
        values = ws.get_all_values()
    except Exception as e:
        await update.message.reply_text(f"⚠️ Can't read sheet: {e}")
        return

    rows = values[1:] if values and values[0] and str(values[0][0]).lower().startswith("timestamp") else values
    my_uid = str(update.effective_user.id)

    total = 0.0
    count = 0
    by_cat = defaultdict(float)

    for r in rows:
        if len(r) < 5:
            continue
        ts_s, uid_s, _username, amt_s, cat = r[0], r[1], r[2], r[3], (r[4] or "").strip() or "uncategorized"
        if not include_all and uid_s != my_uid:
            continue
        ts = parse_ts(ts_s, tz)
        if ts is None or ts < start_dt:
            continue
        amt = parse_amount(str(amt_s))
        if amt is None:
            continue
        total += amt
        count += 1
        by_cat[cat] += amt

    if count == 0:
        labels = {"today": "today", "week": "this week", "month": "this month"}
        scope = "all users" if include_all else "you"
        await update.message.reply_text(f"No expenses for {labels[period]} ({scope}).")
        return

    labels = {"today": "today", "week": "week", "month": "month"}
    scope = "(all users)" if include_all else "(you)"
    lines = [f"📊 Stats for {labels[period]} {scope}", f"Total: {total:.2f}  |  Count: {count}"]
    for cat, s in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"• {cat}: {s:.2f}")
    await update.message.reply_text("\n".join(lines))

# ---------- ERROR HANDLER ----------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ An error occurred. Check logs.")
    except Exception:
        pass

# ---------- APP ----------
def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("expense", cmd_expense))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Step handlers for the simple state machine
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_category, pattern=r"^cat:"))

    app.add_error_handler(on_error)
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
