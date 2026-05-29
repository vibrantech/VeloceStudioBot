import os
import logging
import io
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from PIL import Image, ImageDraw, ImageFont

# Setup logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TOKEN or not RENDER_URL:
    raise ValueError("Missing TELEGRAM_TOKEN or RENDER_EXTERNAL_URL environment variables.")

tg_app = Application.builder().token(TOKEN).build()

# Temporary in-memory storage for user photos (Resets if server restarts, perfect for a simple tool)
user_data_store = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Welcome to **Veloce Studio**! 🚀\n\n"
        "Send me any image as a photo, and I will help you resize it or protect it with a watermark."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves the photo ID and asks the user what they want to do."""
    user_id = update.message.from_user.id
    # Get the highest resolution version of the photo
    photo_file = await update.message.photo[-1].get_file()
    
    # Save file path to user session
    user_data_store[user_id] = {"file_id": photo_file.file_id}

    # Create inline buttons
    keyboard = [
        [
            InlineKeyboardButton("📐 Resize (Width 800px)", callback_data="action_resize"),
            InlineKeyboardButton("🛡️ Add Watermark", callback_data="action_watermark"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("What would you like to do with this asset?", reply_markup=reply_markup)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes button clicks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data

    if user_id not in user_data_store:
        await query.edit_message_text("Session expired. Please send the image again.")
        return

    await query.edit_message_text("⚡ Processing your asset... please wait.")

    try:
        # Download image into memory
        file_id = user_data_store[user_id]["file_id"]
        bot_file = await tg_app.bot.get_file(file_id)
        img_buffer = io.BytesIO()
        await bot_file.download_to_memory(img_buffer)
        img_buffer.seek(0)
        
        # Open with Pillow
        with Image.open(img_buffer) as img:
            # Convert palette/RGBA images to RGB so they save cleanly as JPEG if needed
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            output_buffer = io.BytesIO()

            if action == "action_resize":
                # Scale image keeping aspect ratio (Target width: 800px)
                target_width = 800
                w_percent = target_width / float(img.size[0])
                target_height = int((float(img.size[1]) * float(w_percent)))
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                img.save(output_buffer, format="JPEG", quality=90)
                caption = "📐 Asset resized to 800px width successfully!"

            elif action == "action_watermark":
                # Create a simple text watermark overlay
                draw = ImageDraw.Draw(img)
                # Simple default text positioning (Bottom Right corner)
                width, height = img.size
                text = "© VELOCE STUDIO"
                
                # Draw text shadow/background for visibility
                draw.text((width - 162, height - 32), text, fill=(0, 0, 0))
                draw.text((width - 160, height - 30), text, fill=(255, 255, 255))
                
                img.save(output_buffer, format="JPEG", quality=90)
                caption = "🛡️ Watermark applied successfully!"

            # Send the processed image back to Telegram
            output_buffer.seek(0)
            await tg_app.bot.send_photo(chat_id=user_id, photo=output_buffer, caption=caption)

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        await tg_app.bot.send_message(chat_id=user_id, text="❌ An error occurred while processing your image.")
    
    # Clean up memory
    user_data_store.pop(user_id, None)

# Register handlers
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
tg_app.add_handler(CallbackQueryHandler(handle_buttons))

# FastAPI Webhook Server setup
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await tg_app.initialize()
    webhook_url = f"{RENDER_URL}/webhook"
    await tg_app.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    await tg_app.shutdown()

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def health_check():
    return {"status": "Veloce Studio Bot is online"}
