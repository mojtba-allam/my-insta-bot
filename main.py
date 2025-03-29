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
from storage_handler import StorageHandler

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
        self.storage = StorageHandler()
        self.token = os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_TOKEN environment variable not set")
        
        # Keep track of logged in users
        self.logged_in_users = set()
        # Store Instagram sessions
        self.user_sessions = {}
            
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
            post_url = update.message.text
            context.user_data['post_url'] = post_url
            await update.message.reply_text("⏳ Attempting to download post...")
            
            try:
                # Try downloading without authentication first
                post_data = self.instagram.download_instagram_post(post_url)
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
                error_msg = str(e)
                if "requires authentication" in error_msg:
                    await update.message.reply_text(
                        "🔐 This post requires authentication.\n"
                        "Please provide your Instagram credentials.\n\n"
                        "First, send your Instagram username:"
                    )
                    return WAITING_FOR_USERNAME
                elif "rate limit" in error_msg.lower():
                    await update.message.reply_text(
                        "⏳ Instagram rate limit reached.\n"
                        "Please wait a few minutes and try again."
                    )
                    return ConversationHandler.END
                else:
                    await update.message.reply_text(
                        f"❌ Error: {error_msg}\n"
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
        
        await update.message.reply_text(
            "🔑 Please send your Instagram password.\n"
            "Your credentials will be securely stored for future use."
        )
        return WAITING_FOR_REPOST_PASSWORD
        
    async def process_repost_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process Instagram password and attempt to repost."""
        password = update.message.text
        username = context.user_data.get('instagram_username')
        repost_data = context.user_data.get('repost_data')
        
        # Delete the message containing the password immediately
        await update.message.delete()
        
        if not username or not repost_data:
            await update.message.reply_text("❌ Session expired. Please start over with /start")
            return ConversationHandler.END
        
        try:
            await update.message.reply_text("⏳ Logging in to Instagram...")
            
            # Try to login
            self.poster.login(username, password)
            
            await update.message.reply_text("⏳ Reposting to Instagram...")
            
            # Get original post data
            post_data = context.user_data.get('post_data', {})
            
            # Save media file to MongoDB
            media_path = repost_data['media_path']
            file_id = self.db.save_media_file(media_path, 'photo')
            
            if not file_id:
                raise Exception("Failed to save media file")
            
            # Attempt to post with attribution
            result = self.poster.post_to_instagram(
                media_path=media_path,
                caption=repost_data['caption'],
                original_username=post_data.get('username')
            )
            
            if result['success']:
                # Save post data to MongoDB
                self.db.save_post_data(
                    user_id=update.effective_user.id,
                    post_data=post_data,
                    file_ids=[file_id]
                )
                
                await update.message.reply_text(
                    "✅ Successfully reposted to Instagram!\n"
                    "The post has been saved with attribution.\n\n"
                    f"Caption:\n{result['caption']}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to repost: {result.get('error', 'Unknown error')}\n"
                    "Please try again later."
                )
            
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
                
                await update.message.reply_text(
                    "✅ Successfully logged in!\n\n"
                    "Now you can send me Instagram post URLs to repost them."
                )
                return WAITING_FOR_URL
                
            except Exception as e:
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
        new_caption = update.message.text
        post_data = context.user_data.get('post_data')
        
        if not post_data:
            await update.message.reply_text("❌ Session expired. Please start over with /start")
            return ConversationHandler.END
            
        await update.message.reply_text(
            "✅ Caption saved!\n\n"
            "To repost this content, I'll need your Instagram credentials.\n"
            "Please send your Instagram username:"
        )
        
        # Store caption and post data for later
        try:
            media_path = post_data['media_files'][0]['path']
            if not os.path.exists(media_path):
                await update.message.reply_text(
                    "❌ Error: Media file not found.\n"
                    "Please try downloading the post again."
                )
                return ConversationHandler.END
                
            context.user_data['repost_data'] = {
                'caption': new_caption,
                'media_path': media_path
            }
        except (KeyError, IndexError):
            await update.message.reply_text(
                "❌ Error: Could not find downloaded media.\n"
                "Please try downloading the post again."
            )
            return ConversationHandler.END
        
        return WAITING_FOR_REPOST_USERNAME
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text("Operation cancelled. Send /start to begin again.")
        return ConversationHandler.END
    
    def run(self):
        """Start the bot."""
        app = Application.builder().token(self.token).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                WAITING_FOR_USERNAME: [
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
                CommandHandler('start', self.start),
                CommandHandler('cancel', self.cancel)
            ]
        )
        
        app.add_handler(conv_handler)
        
        # Start the bot
        logger.info("Bot starting...")
        app.run_polling()

if __name__ == '__main__':
    bot = InstaBot()
    bot.run()
