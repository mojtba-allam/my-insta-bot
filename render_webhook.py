#!/usr/bin/env python3
"""
Webhook-based launcher for the Instagram bot on Render.com
"""
import os
import logging
import asyncio
from bot import InstaBot
from dotenv import load_dotenv
import base64
from flask import Flask, request, Response
from threading import Thread

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app for webhook handling
app = Flask(__name__)
BOT_INSTANCE = None

# Function to create credentials file from base64 string if provided
def setup_credentials():
    """Set up credentials.json from environment variable if available."""
    creds_base64 = os.getenv('GOOGLE_DRIVE_CREDENTIALS_BASE64')
    if creds_base64:
        try:
            # Decode base64 credentials
            creds_json = base64.b64decode(creds_base64).decode('utf-8')
            # Write to credentials.json
            with open('credentials.json', 'w') as f:
                f.write(creds_json)
            logger.info("Created credentials.json from environment variable")
            return True
        except Exception as e:
            logger.error(f"Failed to create credentials.json from environment variable: {e}")
    return False

async def setup_bot():
    """Set up and initialize the bot."""
    global BOT_INSTANCE
    
    # Get token from environment or use default
    token = os.getenv('TELEGRAM_TOKEN', "").strip()
    
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable is required")
    
    # Get webhook URL from environment or use default based on Render URL
    webhook_url = os.getenv('WEBHOOK_URL', "")
    if not webhook_url and os.getenv('RENDER_EXTERNAL_URL'):
        webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook/{token}"
    
    if not webhook_url:
        raise ValueError("WEBHOOK_URL or RENDER_EXTERNAL_URL environment variable is required")
    
    # Create a bot instance
    BOT_INSTANCE = InstaBot(token=token)
    
    # Set webhook
    await BOT_INSTANCE.setup_webhook(webhook_url)
    
    logger.info(f"Bot initialized with webhook at {webhook_url}")
    return BOT_INSTANCE

@app.route('/')
def index():
    """Basic healthcheck endpoint."""
    return "Instagram Bot is running in webhook mode!"

@app.route(f'/webhook/<token>', methods=['POST'])
def webhook(token):
    """Handle webhook updates from Telegram."""
    # Verify token
    if token != os.getenv('TELEGRAM_TOKEN', "").strip():
        return Response("Unauthorized", status=403)
    
    # Process update
    if BOT_INSTANCE:
        update_json = request.get_json()
        asyncio.run(BOT_INSTANCE.process_update(update_json))
        return Response("OK", status=200)
    
    return Response("Bot not initialized", status=500)

def main():
    """Main function to start the bot and web server."""
    # Load environment variables
    load_dotenv()
    
    # Set up Google Drive credentials
    setup_credentials()
    
    # Set up the bot asynchronously
    try:
        asyncio.run(setup_bot())
    except Exception as e:
        logger.error(f"Error setting up bot: {e}", exc_info=True)
        return
    
    # Get port from environment or use default
    port = int(os.getenv('PORT', 10000))
    
    # Start the Flask server
    logger.info(f"Starting web server on port {port}")
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
