#!/usr/bin/env python3
"""
Simplified launcher for the Instagram bot.
"""
import os
import logging
from bot import InstaBot
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # Load environment variables
    load_dotenv()
    
    # Get token from environment or use default
    token = os.getenv('TELEGRAM_TOKEN', "7697321641:AAEEwFBLqAtStAnWfjaRmEHhRIFqyBlRuWI")
    
    print(f"Starting Instagram Bot...")
    
    try:
        # Create a bot instance
        bot = InstaBot(token=token)
        
        # Run the bot
        bot.run()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
