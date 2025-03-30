#!/usr/bin/env python3
"""
Simplified launcher for the Instagram bot with async support.
"""
import os
import logging
import asyncio
from bot import InstaBot
from dotenv import load_dotenv
import base64

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

async def main():
    """Run the bot with proper async handling."""
    # Load environment variables
    load_dotenv()
    
    # Check for credentials from environment
    setup_credentials()
    
    # Get token from environment or use default
    token = os.getenv('TELEGRAM_TOKEN', "7697321641:AAEEwFBLqAtStAnWfjaRmEHhRIFqyBlRuWI")
    if '\n' in token:
        # Fix issue with newlines in token
        token = token.strip()
    
    print(f"Starting Instagram Bot...")
    
    try:
        # Create a bot instance
        bot = InstaBot(token=token)
        
        # Run the bot
        await bot.run_async()
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        print(f"Error: {e}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
