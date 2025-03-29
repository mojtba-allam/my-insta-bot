import os
import tempfile
import shutil
import logging
from typing import Dict, Any, Optional
from PIL import Image
import time
import random
from mobile_instagram_client import MobileInstagramClient

logger = logging.getLogger(__name__)

class InstagramPoster:
    """Class to handle Instagram posting."""
    
    def __init__(self):
        self.client = None
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory at {self.temp_dir}")
    
    def login(self, username: str, password: str) -> bool:
        """Login to Instagram."""
        try:
            logger.info("Initializing mobile Instagram client...")
            self.client = MobileInstagramClient()
            
            # Attempt login with our mobile client
            logger.info("Attempting to log in...")
            success = self.client.login(username, password)
            
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
                logger.error("Instagram client not initialized")
                return False
            
            # Determine media type (photo/video)
            is_video = media_path.lower().endswith(('.mp4', '.mov', '.avi'))
            
            # Add attribution to caption if original_url is provided
            if original_url:
                caption = f"{caption}\n\nOriginal: {original_url}"
            
            logger.info(f"Preparing to repost {'video' if is_video else 'photo'} to Instagram")
            
            if is_video:
                # For videos, create a thumbnail
                thumbnail_path = self._create_thumbnail(media_path)
                
                # Upload video
                result = self.client.upload_video(
                    media_path,
                    thumbnail_path,
                    caption=caption
                )
            else:
                # Upload photo
                result = self.client.upload_photo(
                    media_path,
                    caption=caption
                )
            
            logger.info(f"Successfully reposted to Instagram! Media ID: {result.get('media_id')}")
            return True
            
        except Exception as e:
            logger.error(f"Error reposting to Instagram: {str(e)}")
            return False
    
    def _create_thumbnail(self, video_path: str) -> str:
        """Create a thumbnail from the first frame of a video."""
        try:
            import cv2
            
            # Open the video file
            cap = cv2.VideoCapture(video_path)
            
            # Read the first frame
            ret, frame = cap.read()
            
            if not ret:
                raise Exception("Failed to read video frame")
            
            # Create thumbnail path
            thumbnail_path = os.path.join(self.temp_dir, "thumbnail.jpg")
            
            # Save the frame as a JPEG
            cv2.imwrite(thumbnail_path, frame)
            
            # Release the video capture
            cap.release()
            
            return thumbnail_path
        except Exception as e:
            logger.error(f"Error creating video thumbnail: {str(e)}")
            
            # Fallback: generate a black thumbnail
            img = Image.new('RGB', (1080, 1080), color='black')
            thumbnail_path = os.path.join(self.temp_dir, "thumbnail.jpg")
            img.save(thumbnail_path)
            
            return thumbnail_path
    
    def __del__(self):
        """Cleanup method."""
        if self.client:
            try:
                self.client.logout()
            except:
                pass
        
        # Remove temporary directory
        try:
            shutil.rmtree(self.temp_dir)
            logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory: {str(e)}")
