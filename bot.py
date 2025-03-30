"""
Streamlined Telegram Bot for Instagram downloading and reposting.
"""
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram import Update
from telegram.constants import ParseMode
from instagram_manager import InstagramManager
from storage import StorageHandler
import threading
import http.server
import socketserver
import asyncio
import re
from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Add console handler for immediate feedback
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

# States
(WAITING_FOR_URL, WAITING_FOR_USERNAME, WAITING_FOR_PASSWORD,
 WAITING_FOR_CAPTION) = range(4)

class InstaBot:
    """
    A Telegram bot that can download and repost Instagram content.
    """

    def __init__(self, token=None):
        """
        Initialize the bot.
        
        Args:
            token (str, optional): Custom token for the bot. If None, will use TELEGRAM_TOKEN from env.
        """
        # Load environment variables
        load_dotenv()
        
        # Set up token
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_TOKEN environment variable not set")
            
        # Set up Instagram client and storage
        proxy = os.getenv('INSTAGRAM_PROXY')
        
        # Initialize storage with Google Drive support - force it to be enabled
        self.use_google_drive = True  # Always use Google Drive
        self.storage = StorageHandler(
            data_dir=os.getenv('DATA_DIR', 'data'),
            use_google_drive=True,  # Force Google Drive usage
            credentials_file=os.getenv('GOOGLE_DRIVE_CREDENTIALS', 'credentials.json')
        )
        
        # Pass storage handler to Instagram manager
        self.instagram_manager = InstagramManager(proxy=proxy, storage_handler=self.storage)
        
        # Keep track of logged in users
        self.logged_in_users = set()
        # Store Instagram sessions
        self.user_sessions = {}
        
        # Load stored credentials
        self._load_stored_credentials()
            
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the conversation and ask for Instagram credentials."""
        user_id = update.effective_user.id
        
        # Check if already logged in
        if hasattr(self, 'logged_in_users') and user_id in self.logged_in_users:
            await update.message.reply_text(
                "👋 Welcome back to InstaBot!\n\n"
                "You're already logged in. Send me an Instagram post URL to repost it."
            )
            return WAITING_FOR_URL
        
        await update.message.reply_text(
            "👋 Welcome to InstaBot!\n\n"
            "First, let's log in to your Instagram account.\n"
            "Please send your Instagram username:"
        )
        return WAITING_FOR_USERNAME
    
    async def handle_instagram_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle Instagram URLs sent to the bot.
        
        This method downloads the Instagram post and sends it to the user.
        """
        user_id = update.effective_user.id
        
        # Check if URL is in message text
        message_text = update.message.text.strip()
        
        # Log the received URL
        logger.info(f"Received Instagram URL: {message_text}")
        
        if not self._is_instagram_url(message_text):
            await update.message.reply_text("That doesn't look like an Instagram URL. Please send a valid Instagram post URL.")
            return
        
        # Send downloading message
        downloading_message = await update.message.reply_text("⏳ Downloading post...")
        
        try:
            # Get the Instagram credentials
            username = self.user_sessions.get(user_id, {}).get('username')
            password = self.user_sessions.get(user_id, {}).get('password')
            
            if not username or not password:
                await update.message.reply_text(
                    "You need to log in to Instagram first. Use /start to log in."
                )
                return
            
            # Try to download the post directly without using Telegram's media_id parsing
            try:
                # Extract shortcode from URL to avoid any URL parsing issues
                shortcode_match = re.search(r'instagram\.com\/p\/([^\/\?]+)', message_text)
                if not shortcode_match:
                    await update.message.reply_text("Could not extract post ID from URL. Please make sure it's a valid Instagram post URL.")
                    return
                
                shortcode = shortcode_match.group(1)
                logger.info(f"Extracted shortcode: {shortcode}")
                
                # Download the post directly using the Instagram manager
                post_data = self.instagram_manager.download_instagram_post(message_text, username, password)
                
                # Process the downloaded post data
                caption = post_data.get('caption', 'Instagram Post')
                media_files = post_data.get('media_files', [])
                user_info = post_data.get('user_info', {})
                
                if not media_files:
                    raise ValueError("No media found in this post")
                
                # Send the media files
                await self._send_media_files(update, media_files, caption, user_info)
                
                # Edit the downloading message to indicate success
                await downloading_message.edit_text("✅ Download complete!")
                
            except Exception as e:
                # Log the error
                logger.error(f"Error downloading post: {str(e)}")
                
                # Inform the user
                await downloading_message.edit_text(
                    f"❌ Error: {str(e)}\n"
                    "Please try again or contact support if the issue persists."
                )
                
        except Exception as e:
            logger.error(f"Error in handle_instagram_url: {str(e)}")
            await downloading_message.edit_text(
                f"❌ Error: {str(e)}\n"
                "Please try again or contact support if the issue persists."
            )
    
    async def _send_media_files(self, update, media_files, caption, user_info):
        """
        Send downloaded media files to the chat.
        
        Args:
            update (Update): Telegram update object
            media_files (list): List of media file paths
            caption (str): Caption for the media
            user_info (dict): Information about the Instagram user
        """
        if not media_files:
            await update.message.reply_text("No media files to send.")
            return
        
        # Format caption with attribution
        formatted_caption = f"📸 *Instagram Post*\n"
        if user_info and user_info.get('username'):
            formatted_caption += f"👤 @{user_info['username']}\n\n"
        
        formatted_caption += self._escape_markdown(caption[:1000] if caption else "")  # Limit caption length
        
        # If there's only one file, send it directly
        if len(media_files) == 1:
            file_path = media_files[0]
            
            # Check if it's an image or video
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                await update.message.reply_photo(
                    photo=open(file_path, 'rb'),
                    caption=formatted_caption,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            elif file_path.lower().endswith(('.mp4', '.mov')):
                await update.message.reply_video(
                    video=open(file_path, 'rb'),
                    caption=formatted_caption,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_document(
                    document=open(file_path, 'rb'),
                    caption=formatted_caption,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        else:
            # For multiple files, we need to send a media group
            # First send the caption separately as media groups have limited caption support
            await update.message.reply_text(
                formatted_caption,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            # Prepare media group
            media = []
            for file_path in media_files[:10]:  # Telegram limits to 10 files per group
                if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    media.append(InputMediaPhoto(media=open(file_path, 'rb')))
                elif file_path.lower().endswith(('.mp4', '.mov')):
                    media.append(InputMediaVideo(media=open(file_path, 'rb')))
                else:
                    media.append(InputMediaDocument(media=open(file_path, 'rb')))
            
            # Send the media group
            await update.message.reply_media_group(media=media)
    
    def _escape_markdown(self, text):
        """Escape Markdown special characters for Telegram's MARKDOWN_V2 mode."""
        if not text:
            return ""
        
        # Characters that need to be escaped in MARKDOWN_V2
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        # Escape each special character with a backslash
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        
        return text
    
    def _is_instagram_url(self, text):
        """Check if the given text is an Instagram URL."""
        # Handle both www and non-www versions, as well as new Instagram URL formats
        instagram_pattern = re.compile(
            r'https?://(?:www\.)?instagram\.com/(?:p|reel)/[a-zA-Z0-9_-]+/?(?:\?.*)?$'
        )
        return bool(instagram_pattern.match(text))
    
    async def process_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram username for downloading."""
        # Delete the message containing the username for security
        await update.message.delete()
        
        username = update.message.text
        context.user_data['instagram_username'] = username
        
        await update.message.reply_text(
            "Now, please send your Instagram password.\n"
            "🔒 For your security, I'll delete your credentials immediately after use."
        )
        return WAITING_FOR_PASSWORD
    
    async def process_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram password and try to log in."""
        # Delete the message containing the password for security
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete password message: {e}")
        
        try:
            user_id = update.effective_user.id
            username = context.user_data.get('instagram_username')
            password = update.message.text
            
            if not username:
                await update.message.reply_text("❌ Session expired. Please start over with /start")
                return ConversationHandler.END
            
            await update.message.reply_text("🔄 Logging in to Instagram...")
            
            try:
                # Attempt to log in to Instagram
                success = self.instagram_manager.login(username, password)
                
                if success:
                    # Store user info in the user_data
                    context.user_data['instagram'] = {
                        'username': username,
                        'password': password
                    }
                    
                    # Add user to logged in users
                    self.logged_in_users.add(user_id)
                    
                    # Save credentials in user_sessions
                    self.user_sessions[user_id] = {
                        'username': username,
                        'password': password
                    }
                    
                    # Save to storage
                    self.storage.save_credentials(user_id, username, password)
                    
                    await update.message.reply_text(
                        f"✅ Successfully logged in as {username}!\n\n"
                        "Now send me an Instagram post URL to download and repost."
                    )
                    return WAITING_FOR_URL
                else:
                    await update.message.reply_text(
                        "❌ Login failed.\n"
                        "Please check your credentials and try again."
                    )
                    return WAITING_FOR_PASSWORD
                    
            except Exception as e:
                error_message = str(e).lower()
                
                if "network_error" in error_message:
                    await update.message.reply_text(
                        "❌ Network connection error!\n\n"
                        "Could not reach Instagram servers. Please check your internet connection and try again later."
                    )
                elif "challenge_required" in error_message:
                    await update.message.reply_text(
                        "❌ Instagram security challenge required!\n\n"
                        "Please login to your Instagram account through the app or website first to complete any security verifications, then try again."
                    )
                elif "invalid_user" in error_message:
                    await update.message.reply_text(
                        "❌ Invalid Instagram username!\n\n"
                        "The username you provided doesn't seem to exist or might be suspended. Please double-check and try again."
                    )
                elif "bad_password" in error_message:
                    await update.message.reply_text(
                        "❌ Incorrect password!\n\n"
                        "The password you provided is incorrect. Please try again."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Login failed: {str(e)}\n"
                        "Please try again with /start"
                    )
                
                return WAITING_FOR_USERNAME
            
        except Exception as e:
            # Clear sensitive data
            if 'instagram_password' in context.user_data:
                del context.user_data['instagram_password']
            
            await update.message.reply_text(f"❌ Error during login: {str(e)}\nPlease try again with /start")
            return ConversationHandler.END
    
    async def process_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the caption and repost to Instagram."""
        try:
            user_id = update.effective_user.id
            
            # Check if user is logged in
            if user_id not in self.logged_in_users:
                await update.message.reply_text(
                    "❌ You need to log in first.\n"
                    "Please use /start to log in."
                )
                return ConversationHandler.END
            
            # Get post data
            post_data = context.user_data.get('post_data')
            if not post_data:
                await update.message.reply_text(
                    "❌ Post data not found.\n"
                    "Please start over by sending an Instagram post URL."
                )
                return WAITING_FOR_URL
            
            # Get caption
            new_caption = update.message.text
            
            # Upload to Instagram
            await update.message.reply_text("⏳ Reposting to Instagram...")
            
            try:
                # Attempt to repost to Instagram
                result = self.instagram_manager.repost_to_instagram(
                    post_data['local_path'],
                    new_caption,
                    post_data['original_url']
                )
                
                if result and result.get('success'):
                    await update.message.reply_text(
                        "✅ Successfully reposted to Instagram!\n\n"
                        "You can send me another Instagram post URL to repost."
                    )
                else:
                    await update.message.reply_text(
                        "⚠️ Post may have been uploaded, but Instagram did not confirm it.\n"
                        "Please check your Instagram account and try again if needed."
                    )
                
                return WAITING_FOR_URL
                
            except Exception as e:
                logger.error(f"Error reposting to Instagram: {e}", exc_info=True)
                await update.message.reply_text(
                    f"❌ Error reposting to Instagram: {str(e)}\n"
                    "Please try again or contact support if the issue persists."
                )
                return WAITING_FOR_URL
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}\nPlease try again.")
            return WAITING_FOR_URL
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel and end the conversation."""
        await update.message.reply_text(
            "❌ Operation cancelled.\n"
            "You can start over with /start."
        )
        return ConversationHandler.END
    
    async def logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Logout from Instagram."""
        user_id = update.effective_user.id
        
        if user_id in self.logged_in_users:
            # Remove user from logged in users
            self.logged_in_users.remove(user_id)
            
            # Remove session data
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            
            # Remove from storage
            self.storage.delete_credentials(user_id)
            
            # Logout from Instagram
            self.instagram_manager.logout()
            
            await update.message.reply_text(
                "✅ You have been logged out of your Instagram account.\n\n"
                "Use /start to log in again."
            )
        else:
            await update.message.reply_text(
                "You are not currently logged in.\n\n"
                "Use /start to log in."
            )
        
        return ConversationHandler.END
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        await update.message.reply_text(
            "🤔 Need help? Here's a quick guide:\n\n"
            "1. Start by sending /start to begin the conversation.\n"
            "2. Send your Instagram username and password to log in.\n"
            "3. Send an Instagram post URL to download and repost it.\n"
            "4. Send a new caption for the reposted content.\n"
            "5. Use /logout to log out of your Instagram account.\n"
            "6. Use /whoami to view your current Instagram account information.\n\n"
            "If you have any issues or questions, feel free to ask!"
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /status is issued."""
        await update.message.reply_text(
            "🔄 Bot status: Online\n"
            f"📊 Users logged in: {len(self.logged_in_users)}\n"
        )
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors that occur during bot execution."""
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        if update and isinstance(update, Update) and update.effective_message:
            error_message = f"❌ An error occurred: {str(context.error)}"
            await update.effective_message.reply_text(error_message)
    
    async def fallback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle messages that don't match any other handler."""
        await update.message.reply_text(
            "I'm not sure what you mean. Here are the commands you can use:\n\n"
            "/start - Start using the bot and log in to Instagram\n"
            "/help - Show help information\n"
            "/status - Check the bot's status\n"
            "/logout - Log out from your Instagram account\n"
            "/whoami - Show your Instagram account information\n"
            "/cancel - Cancel the current operation"
        )
    
    async def whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display information about the currently logged-in Instagram account."""
        user_id = update.effective_user.id
        
        # Check if the user is logged in
        if user_id not in self.logged_in_users:
            await update.message.reply_text(
                "❌ You are not logged in to any Instagram account.\n"
                "Use /start to log in with your Instagram credentials."
            )
            return WAITING_FOR_USERNAME if context.user_data.get('state') == WAITING_FOR_USERNAME else ConversationHandler.END
        
        # Get user's Instagram credentials from user_sessions (more reliable)
        session_data = self.user_sessions.get(user_id, {})
        username = session_data.get('username', 'Unknown')
        
        logger.debug(f"Retrieved username from session: {username}")
        
        # Attempt to get additional account info if possible
        account_info = "No additional account information available."
        try:
            if hasattr(self.instagram_manager, 'client') and self.instagram_manager.is_logged_in and self.instagram_manager.username == username:
                # Try to get basic account info
                user_info = self.instagram_manager.client.api.username_info(username)
                if user_info and 'user' in user_info:
                    user = user_info['user']
                    account_info = (
                        "<b>Account Details</b>\n"
                        "Full Name: {}\n"
                        "Followers: {}\n"
                        "Following: {}\n"
                        "Posts: {}\n"
                        "Bio: {}"
                    ).format(
                        user.get('full_name', 'Not available'),
                        user.get('follower_count', 'Unknown'),
                        user.get('following_count', 'Unknown'),
                        user.get('media_count', 'Unknown'),
                        user.get('biography', 'No bio')
                    )
        except Exception as e:
            logger.error(f"Error fetching Instagram account details: {str(e)}")
            account_info = "Could not fetch detailed account information."
        
        # Send the response using HTML formatting
        response_text = (
            "<b>Instagram Account Information</b>\n\n"
            "Currently logged in as: <code>" + username + "</code>\n\n"
            + account_info + "\n\n"
            "Use /logout to sign out."
        )
        
        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML
        )
        
        return WAITING_FOR_URL
    
    async def set_commands(self, app):
        """Set up the bot command menu in Telegram."""
        commands = [
            ('start', 'Start the bot and log in to Instagram'),
            ('help', 'Show help information'),
            ('whoami', 'Show your Instagram account information'),
            ('logout', 'Log out from your Instagram account'),
            ('status', 'Check the bot status'),
            ('cancel', 'Cancel the current operation')
        ]
        
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands menu set up successfully")

    def register_handlers(self, app):
        """Register all handlers with the application without starting polling."""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                WAITING_FOR_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_username)
                ],
                WAITING_FOR_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_password)
                ],
                WAITING_FOR_URL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_instagram_url),
                    CommandHandler('logout', self.logout),
                    CommandHandler('whoami', self.whoami),
                ],
                WAITING_FOR_CAPTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_caption),
                    CommandHandler('cancel', self.cancel),
                ]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel),
                CommandHandler('help', self.help_command),
                CommandHandler('logout', self.logout),
                CommandHandler('whoami', self.whoami),
            ],
            name="instagram_conversation"
        )
        
        app.add_handler(conv_handler)
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("logout", self.logout))
        app.add_handler(CommandHandler("whoami", self.whoami))
        
        # Add a global fallback handler for messages not caught by other handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.fallback_handler))
        
        app.add_error_handler(self.error_handler)

    async def run_async(self):
        """Start the bot asynchronously."""
        # Create application instance
        app = Application.builder().token(self.token).concurrent_updates(True).build()
        
        # Explicitly delete webhook to avoid conflicts
        logger.info("Deleting any existing webhook...")
        try:
            import requests
            # Fix possible newline issues in token
            clean_token = self.token.strip()
            response = requests.get(f"https://api.telegram.org/bot{clean_token}/deleteWebhook?drop_pending_updates=true")
            logger.info(f"Webhook deletion response: {response.json()}")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
        
        # Register handlers
        self.register_handlers(app)
        
        # Set up bot commands menu - properly await the coroutine
        await self.set_commands(app)
        
        # Start the bot
        print("Bot starting...")
        logging.info("Bot starting...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        try:
            # Keep the bot running
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            # Handle graceful shutdown
            logger.info("Bot shutting down...")
        finally:
            # Clean shutdown
            await app.stop()
            await app.updater.stop()
            await app.shutdown()
            
    async def setup_webhook(self, webhook_url):
        """Set up webhook mode for the bot."""
        # Create application instance
        app = Application.builder().token(self.token).concurrent_updates(True).build()
        
        # Register handlers
        self.register_handlers(app)
        
        # Set up bot commands menu - properly await the coroutine
        await self.set_commands(app)
        
        # Set webhook
        await app.bot.set_webhook(webhook_url)
        
        # Initialize the app (but don't start polling)
        await app.initialize()
        await app.start()
        
        logger.info(f"Bot webhook set to {webhook_url}")
        return app
    
    async def process_update(self, update_json):
        """Process a single update from the webhook."""
        if not hasattr(self, '_app'):
            # Create application instance if not already created
            self._app = Application.builder().token(self.token).concurrent_updates(True).build()
            
            # Set application attribute to save conversations
            self._app.bot_data['instagram_bot'] = self
            
            # Register handlers
            self.register_handlers(self._app)
            
            # Initialize the app
            await self._app.initialize()
            await self._app.start()
            
            logger.info("Application initialized for webhook processing")
        
        # Create update object
        update = Update.de_json(update_json, self._app.bot)
        
        # Log the update for debugging
        logger.debug(f"Processing update: {update.update_id}")
        
        # Process the update
        await self._app.process_update(update)
        
        # Log completion
        logger.debug(f"Completed processing update: {update.update_id}")
        
    def run(self):
        """Start the bot."""
        # Create application instance
        app = Application.builder().token(self.token).concurrent_updates(True).build()
        
        # Explicitly delete webhook to avoid conflicts
        logger.info("Deleting any existing webhook...")
        try:
            import requests
            response = requests.get(f"https://api.telegram.org/bot{self.token}/deleteWebhook?drop_pending_updates=true")
            logger.info(f"Webhook deletion response: {response.json()}")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
        
        # Register handlers
        self.register_handlers(app)
        
        # Set up bot commands menu
        app.create_task(self.set_commands(app))
        
        # Start the bot
        print("Bot starting...")
        logging.info("Bot starting...")
        app.run_polling(poll_interval=1.0)
        
    def _load_stored_credentials(self):
        """Load stored credentials from storage."""
        try:
            stored_credentials = self.storage.load_all_credentials()
            # Convert list of credentials to a dictionary keyed by user_id
            for creds in stored_credentials:
                if 'user_id' in creds:
                    user_id = int(creds['user_id'])
                    self.user_sessions[user_id] = {
                        'username': creds['username'],
                        'password': creds['password']
                    }
                    self.logged_in_users.add(user_id)
        except Exception as e:
            logging.error(f"Failed to load stored credentials: {e}")

# Simple HTTP request handler for Render
class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Instagram Bot is running!')

def start_web_server():
    """Start a simple web server to keep Render happy"""
    port = int(os.getenv('PORT', 10000))
    handler = SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Web server running on port {port}")
        httpd.serve_forever()

if __name__ == '__main__':
    # Start web server in a separate thread for Render
    if os.getenv('RENDER', 'false').lower() == 'true':
        web_thread = threading.Thread(target=start_web_server)
        web_thread.daemon = True
        web_thread.start()
    
    # Create and start the bot
    bot = InstaBot()
    asyncio.run(bot.run_async())
