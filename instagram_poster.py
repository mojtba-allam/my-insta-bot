import os
import tempfile
import shutil
import logging
from typing import Dict, Any, Optional
from instabot import Bot
from PIL import Image

logger = logging.getLogger(__name__)

class InstagramPoster:
    def __init__(self):
        self.bot = None
        self.temp_dir = tempfile.mkdtemp()
        
    def login(self, username: str, password: str) -> bool:
        """Login to Instagram."""
        try:
            logger.info("Initializing Instagram bot...")
            # Create a new bot instance with optimized settings
            self.bot = Bot(
                base_path=self.temp_dir,
                device_string="android-19.0.0",
                save_logfile=False,
                log_filename=None
            )
            
            # Configure bot settings for faster operation
            self.bot.api.delay_range = [1, 2]  # Minimal delays
            self.bot.api.user_agent = 'Mozilla/5.0 (Linux; Android 12; SM-S906N Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/80.0.3987.119 Mobile Safari/537.36'
            self.bot.api.timeout = 10  # 10 second timeout
            
            logger.info("Attempting to log in...")
            # Attempt login with shorter timeout
            success = self.bot.login(username=username, password=password, use_cookie=False)
            
            if not success:
                logger.error("Login failed: Invalid credentials or Instagram blocked the request")
                raise Exception("Invalid credentials or Instagram blocked the request")
            
            logger.info("Successfully logged in to Instagram!")
            return True
            
        except Exception as e:
            if self.bot:
                self.bot.logout()
            self.bot = None
            raise Exception(f"Login error: {str(e)}")
    
    def post_to_instagram(self, media_path: str, caption: str, original_username: Optional[str] = None) -> Dict[str, Any]:
        """Post media to Instagram with attribution."""
        try:
            if not self.bot:
                logger.error("Attempt to post without being logged in")
                raise Exception("Not logged in to Instagram")
            
            logger.info("Preparing image for upload...")
            # Prepare the image (Instagram requires JPEG)
            img = Image.open(media_path)
            jpeg_path = os.path.join(self.temp_dir, "temp.jpg")
            img.convert('RGB').save(jpeg_path, 'JPEG')
            
            # Always add attribution at the top
            if original_username:
                attribution = f"created by: @{original_username}\n\n"
                caption = attribution + caption
            
            logger.info("Attempting to upload photo to Instagram...")
            # Upload the photo with retry
            for attempt in range(3):  # Try up to 3 times
                try:
                    if self.bot.upload_photo(jpeg_path, caption=caption):
                        logger.info("Successfully posted to Instagram!")
                        return {
                            "success": True,
                            "message": "Successfully posted to Instagram",
                            "caption": caption
                        }
                    else:
                        logger.error(f"Upload attempt {attempt + 1} failed")
                except Exception as upload_error:
                    logger.error(f"Upload error on attempt {attempt + 1}: {str(upload_error)}")
                    if attempt < 2:  # Don't sleep on the last attempt
                        import time
                        time.sleep(3)  # Wait 3 seconds before retrying
            
            raise Exception("Failed to upload after 3 attempts")
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def cleanup(self):
        """Clean up temporary files and logout."""
        try:
            if self.bot:
                self.bot.logout()
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass  # Best effort cleanup
