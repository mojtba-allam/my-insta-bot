import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram import Update
from instagram_handler import InstagramHandler
from instagram_poster import InstagramPoster
from storage import StorageHandler
import threading
import http.server
import socketserver

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
    def __init__(self):
        self.instagram = InstagramHandler()
        self.poster = InstagramPoster()
        
        # Initialize storage with Google Drive support
        self.use_google_drive = os.getenv('USE_GOOGLE_DRIVE', 'false').lower() == 'true'
        self.storage = StorageHandler(
            data_dir=os.getenv('DATA_DIR', 'data'),
            use_google_drive=self.use_google_drive,
            credentials_file=os.getenv('GOOGLE_DRIVE_CREDENTIALS', 'credentials.json')
        )
        
        self.token = os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_TOKEN environment variable not set")
        
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
                    raise Exception("Failed to repost")
                    
            except Exception as e:
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
            
            await update.message.reply_text("⏳ Logging in to Instagram...")
            
            try:
                # Try to login with instagrapi
                self.poster.login(username, password)
                
                # Store the session
                self.logged_in_users.add(user_id)
                self.user_sessions[user_id] = {
                    'username': username,
                    'password': password
                }
                
                # Save credentials to storage
                self.storage.save_credentials(user_id, username, password)
                
                # Check if we have pending repost data
                repost_data = context.user_data.get('repost_data')
                if repost_data:
                    await update.message.reply_text("⏳ Proceeding with repost...")
                    return await self.process_repost_password(update, context)
                
                await update.message.reply_text(
                    "✅ Successfully logged in!\n\n"
                    "Now you can send me Instagram post URLs to repost them."
                )
                return WAITING_FOR_URL
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'challenge_required' in error_msg:
                    await update.message.reply_text(
                        "❌ Login requires additional verification.\n"
                        "Please log in to Instagram app and approve the login request."
                    )
                elif 'bad_password' in error_msg:
                    await update.message.reply_text(
                        "❌ Invalid password.\n"
                        "Please try again with /start"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Login failed: {str(e)}\n"
                        "Please try again with /start"
                    )
                return ConversationHandler.END
            
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
                        self.poster.repost_to_instagram(
                            media_path,
                            new_caption,
                            original_url
                        )
                        
                        await update.message.reply_text(
                            "✅ Successfully reposted to Instagram!\n"
                            "Send another URL to repost more content."
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
        await update.message.reply_text("Operation cancelled. Send /start to begin again.")
        return ConversationHandler.END
    
    def _load_stored_credentials(self):
        """Load stored credentials from storage."""
        try:
            stored_credentials = self.storage.load_all_credentials()
            for user_id, creds in stored_credentials.items():
                self.user_sessions[int(user_id)] = {
                    'username': creds['username'],
                    'password': creds['password']
                }
                self.logged_in_users.add(int(user_id))
        except Exception as e:
            logging.error(f"Failed to load stored credentials: {e}")
    
    def run(self):
        """Start the bot."""
        app = Application.builder().token(self.token).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                WAITING_FOR_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_username)
                ],
                WAITING_FOR_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_password)
                ],
                WAITING_FOR_REPOST_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_repost_username)
                ],
                WAITING_FOR_REPOST_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_repost_password)
                ],
                WAITING_FOR_URL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_url)
                ],
                WAITING_FOR_CAPTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_caption)
                ]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel)
            ]
        )
        
        app.add_handler(conv_handler)
        
        # Start the bot
        print("Bot starting...")
        logging.info("Bot starting...")
        app.run_polling()

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
