import os
import tempfile
import shutil
import logging
from typing import Dict, Any, Optional
from PIL import Image
import time
import random
from robust_instagram_client import RobustInstagramClient

logger = logging.getLogger(__name__)

class InstagramPoster:
    """Class to handle Instagram posting."""
    
    def __init__(self):
        self.client = None
        self.temp_dir = tempfile.mkdtemp()
        
    def login(self, username: str, password: str) -> bool:
        """Login to Instagram."""
        try:
            logger.info("Initializing robust Instagram client...")
            self.client = RobustInstagramClient()
            
            # Attempt login with our robust method
            logger.info("Attempting to log in...")
            success = self.client.robust_login(username, password)
            
            if success:
                logger.info("Successfully logged in to Instagram!")
                return True
            else:
                logger.error("Login failed with no specific error")
                return False
            
        except Exception as e:
            if self.client:
                try:
                    self.client.logout()
                except:
                    pass
                self.client = None
            logger.error(f"Login failed: {str(e)}")
            raise
    
    def repost_to_instagram(self, media_path: str, caption: str, original_url: str = '') -> bool:
        """Repost media to Instagram with attribution."""
        try:
            if not self.client:
                raise Exception("Not logged in to Instagram")
            
            # Ensure media_path is a string, not a PosixPath
            media_path = str(media_path) if media_path else None
            
            if not media_path or not os.path.exists(media_path):
                logger.error(f"Media file not found at path: {media_path}")
                raise Exception("Media file not found")
            
            # Add attribution to caption if original_url is provided
            if original_url:
                caption = f"{caption}\n\nReposted from: {original_url}"
            
            # Check file size
            file_size = os.path.getsize(media_path)
            logger.info(f"Media file size: {file_size} bytes")
            
            # Determine if it's a video by actual file extension
            is_video = media_path.lower().endswith(('.mp4', '.mov'))
            
            # Convert image to JPEG if it's an image
            if not is_video:
                try:
                    with Image.open(media_path) as img:
                        # Create a new path with .jpg extension
                        jpg_path = os.path.splitext(media_path)[0] + '.jpg'
                        # Convert to RGB (in case it's RGBA)
                        if img.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        # Save as JPEG
                        img.convert('RGB').save(jpg_path, 'JPEG', quality=95)
                        media_path = jpg_path
                        logger.info("Converted image to JPEG format")
                except Exception as e:
                    logger.error(f"Failed to convert image: {str(e)}")
                    raise Exception(f"Failed to process image: {str(e)}")
            
            # Upload media
            logger.info("Uploading to Instagram...")
            if is_video:
                self.client.video_upload(media_path, caption=caption)
            else:
                self.client.photo_upload(media_path, caption=caption)
            
            logger.info("Successfully reposted to Instagram!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to repost: {str(e)}")
            if self.client:
                try:
                    self.client.logout()
                except:
                    pass
                self.client = None
            raise
    
    def post_to_instagram(self, media_path: str, caption: str, original_username: Optional[str] = None) -> Dict[str, Any]:
        """Post media to Instagram with attribution."""
        try:
            if not self.client:
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
                    self.client.photo_upload(jpeg_path, caption=caption)
                    logger.info("Successfully posted to Instagram!")
                    return {
                        "success": True,
                        "message": "Successfully posted to Instagram",
                        "caption": caption
                    }
                except Exception as upload_error:
                    logger.error(f"Upload error on attempt {attempt + 1}: {str(upload_error)}")
                    if attempt < 2:  # Don't sleep on the last attempt
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
            if self.client:
                self.client.logout()
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass  # Best effort cleanup
