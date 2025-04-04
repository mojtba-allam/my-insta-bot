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
from instagram_handler import InstagramHandler
from instagram_poster import InstagramPoster
from storage import StorageHandler
import threading
import http.server
import socketserver

# Check if we're running on Render and need to set up credentials
if os.getenv('RENDER', 'false').lower() == 'true':
    try:
        from render_setup import setup_credentials
        setup_credentials()
        print("Successfully set up credentials from environment variables")
    except Exception as e:
        print(f"Error setting up credentials: {e}")

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG level
)
logger = logging.getLogger(__name__)

# Add console handler for immediate feedback
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

# States
(WAITING_FOR_URL, WAITING_FOR_USERNAME, WAITING_FOR_PASSWORD,
 WAITING_FOR_CAPTION, WAITING_FOR_REPOST_USERNAME, WAITING_FOR_REPOST_PASSWORD) = range(6)

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
            
        # Set up storage and user sessions
        self.instagram = InstagramHandler()
        self.poster = InstagramPoster()
        
        # Initialize storage with Google Drive support
        self.use_google_drive = os.getenv('USE_GOOGLE_DRIVE', 'false').lower() == 'true'
        self.storage = StorageHandler(
            data_dir=os.getenv('DATA_DIR', 'data'),
            use_google_drive=self.use_google_drive,
            credentials_file=os.getenv('GOOGLE_DRIVE_CREDENTIALS', 'credentials.json')
        )
        
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
        
    async def process_repost_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram username for reposting."""
        username = update.message.text
        context.user_data['instagram_username'] = username
        context.user_data['login_in_progress'] = True
        
        await update.message.reply_text(
            "🔑 Please send your Instagram password.\n"
            "Your credentials will be securely stored for future use."
        )
        return WAITING_FOR_REPOST_PASSWORD
        
    async def process_repost_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram password and attempt to repost."""
        try:
            password = update.message.text
            username = context.user_data.get('instagram_username')
            user_id = update.effective_user.id
            
            # Delete the message containing the password immediately
            await update.message.delete()
            
            if not username or not context.user_data.get('login_in_progress'):
                await update.message.reply_text("❌ Invalid login attempt. Please use /start to begin.")
                return ConversationHandler.END
            
            await update.message.reply_text("🔄 Logging in to Instagram...")
            
            try:
                # Try to login
                self.poster.login(username, password)
                
                # Store the session
                self.logged_in_users.add(user_id)
                self.user_sessions[user_id] = {
                    'username': username,
                    'password': password
                }
                
                # Save credentials to storage
                self.storage.save_credentials(user_id, username, password)
                
                # Clear login flag
                context.user_data['login_in_progress'] = False
                
                # Get repost data
                repost_data = context.user_data.get('repost_data', {})
                if not repost_data:
                    await update.message.reply_text(
                        "✅ Successfully logged in!\n\n"
                        "Now you can send me Instagram post URLs to repost them."
                    )
                    return WAITING_FOR_URL
                
                await update.message.reply_text("⏳ Reposting to Instagram...")
                
                # Get media path and caption
                media_path = repost_data.get('media_path')
                caption = repost_data.get('caption')
                original_url = repost_data.get('original_url', '')
                
                if not media_path or not caption:
                    raise Exception("Missing media path or caption")
                
                # Attempt to repost
                success = self.poster.repost_to_instagram(
                    media_path=media_path,
                    caption=caption,
                    original_url=original_url
                )
                
                if success:
                    await update.message.reply_text(
                        "✅ Successfully reposted to Instagram!\n"
                        "Send another URL to repost more content."
                    )
                    return WAITING_FOR_URL
                else:
                    logging.error("Instagram posting returned False")
                    await update.message.reply_text(
                        "❌ Failed to post to Instagram. Check logs for details.\n"
                        "You can try again by sending another URL."
                    )
                    return WAITING_FOR_URL
                    
            except Exception as e:
                logging.error(f"Exception during Instagram posting: {str(e)}", exc_info=True)
                await update.message.reply_text(
                    f"❌ Error: {str(e)}\n"
                    "Please try again with /start"
                )
                return ConversationHandler.END
                
        except Exception as e:
            await update.message.reply_text(
                "❌ An error occurred. Please try again with /start"
            )
            return ConversationHandler.END
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        # Clean up
        self.poster.cleanup()
        
        # Clear sensitive data
        if 'instagram_username' in context.user_data:
            del context.user_data['instagram_username']
        if 'repost_data' in context.user_data:
            del context.user_data['repost_data']
        
        return ConversationHandler.END
    
    async def process_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram password for initial login."""
        # Delete the message containing the password for security
        await update.message.delete()
        
        try:
            password = update.message.text
            username = context.user_data.get('instagram_username')
            user_id = update.effective_user.id
            
            if not username:
                await update.message.reply_text("❌ Session expired. Please start over with /start")
                return ConversationHandler.END
            
            await update.message.reply_text("🔄 Logging in to Instagram...")
            
            try:
                # Attempt to log in to Instagram
                success = self.poster.login(username, password)
                
                if success:
                    # Store user info in the user_data
                    context.user_data['instagram'] = {
                        'username': username,
                        'password': password
                    }
                    
                    # Add user to logged in users
                    self.logged_in_users.add(user_id)
                    
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
            context.user_data.pop('instagram_username', None)
            
            await update.message.reply_text(
                f"❌ Authentication failed: {str(e)}\n"
                "Please try again with /start"
            )
            return ConversationHandler.END
    
    async def process_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Save the new caption and prepare for reposting."""
        try:
            new_caption = update.message.text
            post_data = context.user_data.get('post_data')
            user_id = update.effective_user.id
            
            if not post_data:
                await update.message.reply_text("❌ Session expired. Please start over with /start")
                return ConversationHandler.END
            
            # Store caption and post data for later
            try:
                # Get the first media file path
                media_files = post_data.get('media_files', [])
                if not media_files:
                    raise KeyError("No media files found")
                    
                media_path = media_files[0]['path']
                original_url = post_data.get('original_url', '')
                
                if not os.path.exists(media_path):
                    await update.message.reply_text(
                        "❌ Error: Media file not found.\n"
                        "Please try downloading the post again."
                    )
                    return ConversationHandler.END
                    
                # Store repost data
                context.user_data['repost_data'] = {
                    'caption': new_caption,
                    'media_path': media_path,
                    'original_url': original_url
                }
            except (KeyError, IndexError) as e:
                await update.message.reply_text(
                    "❌ Error: Could not find downloaded media.\n"
                    "Please try downloading the post again."
                )
                logger.error(f"Failed to process media: {str(e)}")
                return ConversationHandler.END
            
            # Check if user is already logged in
            if user_id in self.logged_in_users:
                session = self.user_sessions.get(user_id)
                if session:
                    await update.message.reply_text("⏳ Reposting to Instagram...")
                    try:
                        # Ensure we're logged in with current session
                        self.poster.login(session['username'], session['password'])
                        
                        # Attempt to repost
                        success = self.poster.repost_to_instagram(
                            media_path,
                            new_caption,
                            original_url
                        )
                        
                        if success:
                            await update.message.reply_text(
                                "✅ Successfully reposted to Instagram!\n"
                                "Send another URL to repost more content."
                            )
                            return WAITING_FOR_URL
                        else:
                            logging.error("Instagram posting returned False")
                            await update.message.reply_text(
                                "❌ Failed to post to Instagram. Check logs for details.\n"
                                "You can try again by sending another URL."
                            )
                            return WAITING_FOR_URL
                    except Exception as e:
                        # If repost fails, remove user from logged in users and ask to log in again
                        self.logged_in_users.remove(user_id)
                        await update.message.reply_text(
                            f"❌ Repost failed: {str(e)}\n"
                            "Please log in again."
                        )
            
            # If we get here, user needs to log in
            await update.message.reply_text(
                "✅ Caption saved!\n\n"
                "Please send your Instagram username to proceed:"
            )
            return WAITING_FOR_REPOST_USERNAME
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ An error occurred: {str(e)}\n"
                "Please try again with /start"
            )
            return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            "Operation cancelled.\n\n"
            "Use /start to begin again."
        )
        return ConversationHandler.END
        
    async def logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Log out the user from their Instagram account."""
        user_id = update.effective_user.id
        
        if user_id in self.logged_in_users:
            self.logged_in_users.remove(user_id)
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            
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
            "📊 Users logged in: {}\n".format(len(self.logged_in_users))
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
        logger.debug(f"User sessions: {self.user_sessions}")
        
        # Attempt to get additional account info if possible
        account_info = "No additional account information available."
        try:
            if hasattr(self.poster, 'api') and self.poster.is_logged_in and self.poster.username == username:
                # Try to get basic account info
                user_info = self.poster.api.username_info(username)
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
        """Register all handlers with the application without starting polling.
        This allows using the bot with different run methods (polling or webhook).
        """
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
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_caption)
                ],
                WAITING_FOR_REPOST_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_repost_username)
                ],
                WAITING_FOR_REPOST_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_repost_password)
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
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
        # Create a unique session name with timestamp to avoid conflicts
        import time
        session_name = f"insta_bot_{int(time.time())}"
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
    
    # Start the Telegram bot
    bot = InstaBot()
    bot.run()
