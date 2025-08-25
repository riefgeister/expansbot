# Telegram Expense Bot on Render (Webhook)

This repo contains a minimal Telegram bot that records expenses into Google Sheets.
It is ready to deploy to Render on the free plan.

## What you'll need
- Telegram bot token from @BotFather
- A Google Sheet (get its Spreadsheet ID from the URL)
- A Google Cloud service account with access to that sheet, **Editor** role
- The service account JSON (we'll paste it into an env var)

## 1) Prepare Google Sheets access
1. Create a service account in Google Cloud (enable Google Sheets and Drive APIs).
2. Download the JSON key.
3. Share your Google Sheet with the service account email (Editor).
4. Copy the Spreadsheet ID (the part between `/d/` and `/edit`).

## 2) Local quick test (optional)
- Create a `.env` with:
  BOT_TOKEN=...
  SPREADSHEET_ID=...
  WORKSHEET_NAME=Sheet1
  GOOGLE_CREDENTIALS_JSON=<paste the entire JSON in one line>

- Run:
  pip install -r requirements.txt
  python bot_expense.py
  (talk to your bot and try /expense)

## 3) Deploy to Render
1. Push this repo to GitHub.
2. In Render: New -> Blueprint -> select this repo (render.yaml will be detected).
3. After the first deploy, open the service -> Environment and set these variables:
   - BOT_TOKEN
   - SPREADSHEET_ID
   - WORKSHEET_NAME (optional, default Sheet1)
   - GOOGLE_CREDENTIALS_JSON (paste the whole JSON)
   - BASE_URL = https://<your-service-name>.onrender.com
4. Click "Clear cache & deploy".
   On startup the app sets the Telegram webhook to BASE_URL + `/telegram/<BOT_TOKEN>`.

## 4) Use
- Open your bot in Telegram and send `/expense`
- Enter amount (e.g., `12.50`)
- Click a category button (`food`, `household`, `rent`)
- The row is appended to your Google Sheet:
  Timestamp | TelegramUserID | Username | Amount | Category

## Troubleshooting
- If you change BASE_URL or the bot token, redeploy to refresh the webhook.
- Check Render logs if you see no responses from the bot.
- Ensure your Sheet is shared with the service account email.

