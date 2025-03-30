"""
Combined Instagram handler and poster functionality.
This file merges instagram_handler.py and instagram_poster.py.
"""
import os
import re
import time
import json
import logging
import requests
from io import BytesIO
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image
from instagram_client import MobileInstagramClient

# Configure logging
logger = logging.getLogger(__name__)

class InstagramManager:
    """
    Combined Instagram handler class for downloading and posting content.
    """
    
    def __init__(self, proxy=None, storage_handler=None):
        """
        Initialize the Instagram handler and poster.
        
        Args:
            proxy (str, optional): Proxy URL for requests.
            storage_handler: Storage handler for saving data to Google Drive
        """
        self.client = MobileInstagramClient(proxy=proxy, storage_handler=storage_handler)
        self.storage_handler = storage_handler
        self.is_logged_in = False
        self.username = None
        self.post_data = {}
    
    def login(self, username, password, force_login=False):
        """
        Login to Instagram using the mobile API.
        
        Args:
            username (str): Instagram username
            password (str): Instagram password
            force_login (bool, optional): Whether to force a fresh login
            
        Returns:
            bool: True if login was successful, False otherwise
        """
        try:
            success = self.client.login(username, password, force_login)
            if success:
                self.is_logged_in = True
                self.username = username
            return success
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            raise
    
    def logout(self):
        """Logout from Instagram."""
        if self.client:
            return self.client.logout()
        return True
    
    def download_instagram_post(self, post_url: str, instagram_username: Optional[str] = None, 
                               instagram_password: Optional[str] = None) -> Dict[str, Any]:
        """
        Download an Instagram post and return its metadata.
        
        Args:
            post_url (str): URL of the Instagram post
            instagram_username (str, optional): Instagram username for authentication
            instagram_password (str, optional): Instagram password for authentication
            
        Returns:
            dict: Post metadata
        """
        # Validate URL format
        if not self._validate_instagram_url(post_url):
            raise ValueError("Invalid Instagram URL format")
        
        # Extract post ID or shortcode
        post_id = self._extract_post_id(post_url)
        if not post_id:
            raise ValueError("Could not extract post ID from URL")
        
        logger.debug(f"Extracted post ID/shortcode: {post_id}")
        
        # Check login status and login if credentials provided
        if not self.is_logged_in and instagram_username and instagram_password:
            self.login(instagram_username, instagram_password)
        
        # If we're still not logged in, raise an error
        if not self.is_logged_in:
            raise Exception("Login required to download this post")
        
        try:
            # Get post info - try different methods based on the ID format
            media_info = None
            
            try:
                # Try using media_info method (requires numeric ID)
                media_info = self.client.api.media_info(post_id)
            except Exception as first_error:
                logger.debug(f"Error using media_info with ID {post_id}: {str(first_error)}")
                
                try:
                    # Try getting media info by URL
                    media_info = self.client.api.media_info_by_url(post_url)
                except Exception as second_error:
                    logger.debug(f"Error using media_info_by_url: {str(second_error)}")
                    
                    try:
                        # Try getting media info by shortcode
                        media_info = self.client.api.media_info_by_code(post_id)
                    except Exception as third_error:
                        logger.debug(f"Error using media_info_by_code: {str(third_error)}")
                        # Re-raise the original error
                        raise first_error
            
            # Extract media data
            items = media_info.get('items', [])
            if not items:
                raise ValueError("Post not found or is private")
            
            post_data = items[0]
            
            # Extract media URL
            media_url = None
            media_type = None
            
            if post_data.get('media_type') == 1:  # Photo
                media_type = 'photo'
                media_url = post_data.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
            elif post_data.get('media_type') == 2:  # Video
                media_type = 'video'
                media_url = post_data.get('video_versions', [{}])[0].get('url')
            elif post_data.get('media_type') == 8:  # Album/carousel
                media_type = 'carousel'
                # Get first item by default
                carousel_items = post_data.get('carousel_media', [])
                if carousel_items:
                    first_item = carousel_items[0]
                    if first_item.get('media_type') == 1:
                        media_url = first_item.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
                    elif first_item.get('media_type') == 2:
                        media_url = first_item.get('video_versions', [{}])[0].get('url')
            
            if not media_url:
                raise ValueError("Could not extract media URL from post")
            
            # Download the media
            local_path = self._download_media(media_url, post_id, media_type)
            
            # Extract metadata
            username = post_data.get('user', {}).get('username', 'unknown')
            caption = post_data.get('caption', {})
            caption_text = caption.get('text', '') if caption else ''
            
            # Store post data for later use
            self.post_data = {
                'id': post_id,
                'media_url': media_url,
                'local_path': local_path,
                'media_type': media_type,
                'username': username,
                'caption': caption_text,
                'likes': post_data.get('like_count', 0),
                'comments': post_data.get('comment_count', 0),
                'timestamp': post_data.get('taken_at', 0),
                'original_url': post_url
            }
            
            return self.post_data
            
        except Exception as e:
            logger.error(f"Error downloading Instagram post: {str(e)}")
            raise
    
    def repost_to_instagram(self, media_path: str, caption: str, original_url: str = ''):
        """
        Repost media to Instagram with a custom caption.
        
        Args:
            media_path (str): Path to the media file
            caption (str): Caption for the post
            original_url (str, optional): Original post URL for reference
            
        Returns:
            dict: Result of the upload operation
        """
        if not self.is_logged_in:
            raise Exception("You must be logged in to repost content")
        
        if not os.path.exists(media_path):
            raise ValueError(f"Media file not found: {media_path}")
        
        try:
            # Process the image to ensure compatibility
            processed_path = self._process_image_for_instagram(media_path)
            
            # Upload the photo with caption
            logger.info(f"Uploading photo to Instagram with caption: {caption[:50]}...")
            upload_result = self.client.upload_photo(processed_path, caption=caption)
            
            # Debug the upload result
            logger.debug(f"Upload result: {json.dumps(upload_result, indent=2)}")
            
            # Validate the upload result
            if not upload_result or not isinstance(upload_result, dict):
                logger.error("Invalid upload result received")
                raise Exception("Upload failed with invalid response")
            
            # Check if the upload was successful
            if upload_result.get('status') == 'ok':
                media_id = upload_result.get('media', {}).get('id', 'unknown')
                logger.info(f"Successfully posted to Instagram with media ID: {media_id}")
                
                # Check if the media is actually present in the response
                if 'media' in upload_result and upload_result['media']:
                    logger.info("Media object found in response, upload confirmed")
                else:
                    logger.warning("Media object not found in response, upload status unclear")
                
                return {
                    'success': True,
                    'media_id': media_id,
                    'original_url': original_url
                }
            else:
                error_message = upload_result.get('message', 'Unknown error')
                logger.error(f"Upload failed with status: {upload_result.get('status')} - {error_message}")
                raise Exception(f"Upload failed: {error_message}")
            
        except Exception as e:
            logger.error(f"Error reposting to Instagram: {str(e)}")
            raise
    
    def _validate_instagram_url(self, url: str) -> bool:
        """Validate that the URL is from Instagram."""
        instagram_patterns = [
            r'https?://(?:www\.)?instagram\.com/p/[a-zA-Z0-9_-]+/?',
            r'https?://(?:www\.)?instagram\.com/reel/[a-zA-Z0-9_-]+/?'
        ]
        
        for pattern in instagram_patterns:
            if re.match(pattern, url):
                return True
        
        return False
    
    def _extract_post_id(self, url: str) -> Optional[str]:
        """Extract post ID from Instagram URL."""
        # First clean up the URL by removing query parameters
        if '?' in url:
            url = url.split('?')[0]
        
        # Try to extract the shortcode from the URL
        patterns = [
            r'instagram\.com/p/([a-zA-Z0-9_-]+)',
            r'instagram\.com/reel/([a-zA-Z0-9_-]+)'
        ]
        
        shortcode = None
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                shortcode = match.group(1)
                break
        
        if not shortcode:
            return None
        
        # Convert the shortcode to a numeric ID - Instagram API expects numeric IDs
        try:
            # If we have an authenticated client, use the media_id_to_code method in reverse
            if hasattr(self, 'client') and self.client.is_logged_in:
                # First try using API to get info directly with shortcode
                try:
                    media_info = self.client.api.media_info_by_url(url)
                    if media_info and 'items' in media_info and media_info['items']:
                        return str(media_info['items'][0]['id'])
                except Exception as e:
                    logger.debug(f"Could not get media info by URL, trying shortcode: {e}")
                
                # Try using the internal method to convert shortcode to media_id
                try:
                    # This is a hacky way to access the private method
                    from instagram_private_api.compatpatch import ClientCompatPatch
                    media_id = ClientCompatPatch.media_id(shortcode)
                    return media_id
                except Exception as e:
                    logger.debug(f"Could not convert shortcode to media_id: {e}")
            
            # If all else fails, return the shortcode itself
            return shortcode
        except Exception as e:
            logger.error(f"Error extracting numeric post ID: {str(e)}")
            return shortcode  # Return the shortcode as fallback
    
    def _download_media(self, url: str, post_id: str, media_type: str) -> str:
        """
        Download media from URL and save it locally.
        
        Args:
            url (str): URL of the media
            post_id (str): Instagram post ID
            media_type (str): Type of media (photo, video, carousel)
            
        Returns:
            str: Path to the downloaded file
        """
        # Create downloads directory if it doesn't exist
        os.makedirs("downloads", exist_ok=True)
        
        # Determine file extension
        if media_type == 'photo':
            ext = 'jpg'
        elif media_type == 'video':
            ext = 'mp4'
        else:
            ext = 'jpg'  # Default to jpg for unknown types
        
        # Generate local path
        local_path = f"downloads/{post_id}.{ext}"
        
        # Download the file
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # If we have a storage handler, save directly to Google Drive
            if self.storage_handler and self.storage_handler.use_google_drive:
                file_name = f"{post_id}.{ext}"
                file_data = response.content
                
                try:
                    # Save to Google Drive
                    mime_type = "image/jpeg" if ext == "jpg" else "video/mp4"
                    self.storage_handler.google_drive.upload_file_data(
                        file_name=file_name,
                        file_data=file_data,
                        mime_type=mime_type
                    )
                    logger.info(f"Media saved to Google Drive: {file_name}")
                except Exception as e:
                    logger.error(f"Error saving media to Google Drive: {str(e)}")
            
            # Also save locally as a fallback/cache
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            
            logger.info(f"Downloaded media to {local_path}")
            return local_path
        else:
            raise Exception(f"Failed to download media: {response.status_code}")
    
    def _process_image_for_instagram(self, image_path: str) -> str:
        """
        Process the image to ensure it's compatible with Instagram.
        
        Args:
            image_path (str): Path to the image
            
        Returns:
            str: Path to the processed image
        """
        try:
            # Open the image
            img = Image.open(image_path)
            
            # Ensure image is in RGB mode (remove alpha channel)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # Create new RGB image with white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Generate output path
            output_path = f"{os.path.splitext(image_path)[0]}_processed.jpg"
            
            # Save the processed image
            img.save(output_path, 'JPEG', quality=95)
            
            logger.info(f"Processed image saved to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            # If processing fails, return the original path
            return image_path
