import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# 1. Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Retrieve Environment Variables from Render
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") # Automatically provided by Render

if not TOKEN or not RENDER_URL:
    raise ValueError("Missing TELEGRAM_TOKEN or RENDER_EXTERNAL_URL environment variables.")

# 3. Initialize Telegram Application
tg_app = Application.builder().token(TOKEN).build()

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Welcome to Veloce Studio! 🚀\n\n"
        "Send me any image, and I will help you scale and protect your assets."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Placeholder for handling images."""
    await update.message.reply_text("Image received! Processing engine initializing...")

# Register handlers
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(MessageHandler(filters.PHOTO, handle_image))

# --- FASTAPI WEBHOOK LIFECYCLE ---
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    """Connects the webhook when Render starts the app."""
    await tg_app.initialize()
    webhook_url = f"{RENDER_URL}/webhook"
    await tg_app.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook successfully set to: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    """Cleans up when the app stops."""
    await tg_app.shutdown()

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Receives updates from Telegram and passes them to the bot."""
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def health_check():
    """Simple route to confirm the server is running."""
    return {"status": "Veloce Studio Bot is online"}
