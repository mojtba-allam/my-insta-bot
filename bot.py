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
        self.instagram = InstagramManager(proxy=proxy, storage_handler=self.storage)
        
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
    
    async def process_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the Instagram URL and download the post."""
        try:
            user_id = update.effective_user.id
            
            # Check if user is logged in
            if user_id not in self.logged_in_users:
                await update.message.reply_text(
                    "❌ You need to log in first.\n"
                    "Please use /start to log in."
                )
                return ConversationHandler.END
            
            post_url = update.message.text
            context.user_data['post_url'] = post_url
            await update.message.reply_text("⏳ Downloading post...")
            
            try:
                # Get session if available
                session = self.user_sessions.get(user_id)
                username = session['username'] if session else None
                password = session['password'] if session else None
                
                # Try downloading with current session if available
                post_data = self.instagram.download_instagram_post(
                    post_url,
                    instagram_username=username,
                    instagram_password=password
                )
                
                context.user_data['post_data'] = post_data
                
                # If successful, ask for new caption
                await update.message.reply_text(
                    f"✅ Downloaded post from @{post_data['username']}\n\n"
                    f"Original caption:\n{post_data['caption']}\n\n"
                    "Please send me the new caption for reposting."
                )
                return WAITING_FOR_CAPTION
                
            except ValueError as e:
                # Handle validation errors (invalid URL, post not found)
                await update.message.reply_text(f"❌ {str(e)}")
                return WAITING_FOR_URL
                
            except Exception as e:
                error_msg = str(e).lower()
                if "login required" in error_msg or "login_required" in error_msg:
                    await update.message.reply_text(
                        "🔐 This post requires authentication.\n"
                        "Please provide your Instagram credentials.\n\n"
                        "First, send your Instagram username:"
                    )
                    return WAITING_FOR_USERNAME
                elif "rate limit" in error_msg:
                    await update.message.reply_text(
                        "⏳ Instagram rate limit reached.\n"
                        "Please wait a few minutes and try again."
                    )
                    return ConversationHandler.END
                elif "challenge_required" in error_msg:
                    await update.message.reply_text(
                        "❌ Login requires verification.\n"
                        "Please log in to Instagram app and approve the login request."
                    )
                    return ConversationHandler.END
                else:
                    await update.message.reply_text(
                        f"❌ Error: {str(e)}\n"
                        "Please try again or contact support if the issue persists."
                    )
                    return WAITING_FOR_URL
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}\nPlease try again with a valid Instagram post URL.")
            return WAITING_FOR_URL
    
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
                success = self.instagram.login(username, password)
                
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
                result = self.instagram.repost_to_instagram(
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
            self.instagram.logout()
            
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
            if hasattr(self.instagram, 'client') and self.instagram.is_logged_in and self.instagram.username == username:
                # Try to get basic account info
                user_info = self.instagram.client.api.username_info(username)
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
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_url),
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
