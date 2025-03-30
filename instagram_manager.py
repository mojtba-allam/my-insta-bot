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
    
    def _extract_shortcode_from_url(self, url: str) -> str:
        """
        Extract the Instagram post shortcode from a URL.
        
        Args:
            url (str): Instagram post URL
            
        Returns:
            str: Shortcode
        """
        # Clean the URL first - remove any query parameters
        url = url.split('?')[0].strip('/')
        
        # Handle different URL formats
        patterns = [
            r'instagram\.com/p/([A-Za-z0-9_-]+)',
            r'instagram\.com/reel/([A-Za-z0-9_-]+)',
            r'instagram\.com/tv/([A-Za-z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # If no match found
        raise ValueError(f"Could not extract shortcode from URL: {url}")
    
    def get_media_info_by_shortcode(self, shortcode: str) -> Dict[str, Any]:
        """
        Get complete media information for an Instagram post using its shortcode.
        Uses multiple approaches for maximum compatibility.
        
        Args:
            shortcode (str): Instagram post shortcode
            
        Returns:
            dict: Media information
        """
        # Logging for debugging
        logger.info(f"Fetching media info for shortcode: {shortcode}")
        
        # Try multiple approaches to get media info
        errors = []
        
        # Approach 1: Use our custom shortcode method from instagram_client
        try:
            media_info = self.client.get_media_by_shortcode(shortcode)
            if media_info and media_info.get('items'):
                logger.info("Successfully got media info using get_media_by_shortcode")
                return media_info
        except Exception as e:
            error_msg = f"Error using get_media_by_shortcode: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
        
        # Approach 2: Try direct web scraping as a fallback
        try:
            import requests
            from bs4 import BeautifulSoup
            import json
            
            # Try to fetch the page and extract JSON data
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            url = f"https://www.instagram.com/p/{shortcode}/"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                # Try to find shared data in the HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                scripts = soup.find_all('script')
                
                for script in scripts:
                    if script.string and '_sharedData = ' in script.string:
                        json_text = script.string.split('_sharedData = ')[1].split(';</script>')[0]
                        data = json.loads(json_text)
                        
                        # Extract post data from shared data
                        post_page = data.get('entry_data', {}).get('PostPage', [{}])[0]
                        media = post_page.get('graphql', {}).get('shortcode_media', {})
                        
                        if media:
                            # Convert to format similar to API response
                            username = media.get('owner', {}).get('username', 'unknown')
                            caption_text = ''
                            edges = media.get('edge_media_to_caption', {}).get('edges', [])
                            if edges and len(edges) > 0:
                                caption_text = edges[0].get('node', {}).get('text', '')
                            
                            # Construct media info in API-like format
                            synthetic_media_info = {
                                'items': [{
                                    'id': media.get('id'),
                                    'code': shortcode,
                                    'media_type': 1 if media.get('__typename') == 'GraphImage' else 2,
                                    'image_versions2': {
                                        'candidates': [{'url': media.get('display_url')}]
                                    },
                                    'video_versions': [{'url': media.get('video_url')}] if media.get('is_video') else [],
                                    'carousel_media': self._extract_carousel_items(media) if media.get('__typename') == 'GraphSidecar' else [],
                                    'caption': {'text': caption_text},
                                    'user': {
                                        'username': username,
                                        'full_name': media.get('owner', {}).get('full_name', ''),
                                    }
                                }]
                            }
                            
                            logger.info("Successfully got media info using web scraping")
                            return synthetic_media_info
            
            error_msg = f"Web scraping failed to extract post data: {response.status_code}"
            logger.warning(error_msg)
            errors.append(error_msg)
            
        except Exception as e:
            error_msg = f"Error using web scraping approach: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
        
        # If we reach here, all approaches failed
        error_details = "\n".join(errors)
        logger.error(f"All approaches to get media info failed:\n{error_details}")
        raise Exception(f"Failed to get media info for shortcode {shortcode}")
    
    def _extract_carousel_items(self, media):
        """Extract carousel items from web API response."""
        carousel_items = []
        edges = media.get('edge_sidecar_to_children', {}).get('edges', [])
        
        for edge in edges:
            node = edge.get('node', {})
            item = {
                'id': node.get('id'),
                'media_type': 1 if node.get('__typename') == 'GraphImage' else 2,
                'image_versions2': {
                    'candidates': [{'url': node.get('display_url')}]
                },
            }
            
            if node.get('is_video'):
                item['video_versions'] = [{'url': node.get('video_url')}]
                
            carousel_items.append(item)
            
        return carousel_items
    
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
        
        # Extract shortcode directly from the URL
        try:
            shortcode = self._extract_shortcode_from_url(post_url)
            logger.info(f"Extracted shortcode from URL: {shortcode}")
        except Exception as e:
            logger.error(f"Error extracting shortcode: {e}")
            raise ValueError(f"Could not extract shortcode from URL: {post_url}")
        
        # Check login status and login if credentials provided
        if not self.is_logged_in and instagram_username and instagram_password:
            self.login(instagram_username, instagram_password)
        
        # If we're still not logged in, raise an error
        if not self.is_logged_in:
            raise Exception("Login required to download this post")
        
        try:
            # Get media info using our improved method
            media_info = self.get_media_info_by_shortcode(shortcode)
            
            # Extract media data
            items = media_info.get('items', [])
            if not items:
                raise ValueError("Post not found or is private")
            
            media_item = items[0]
            
            # Get media type and URL
            media_type = media_item.get('media_type', 1)
            is_carousel = media_type == 8 or 'carousel_media' in media_item
            is_video = media_type == 2 or 'video_versions' in media_item
            
            # Get post information
            username = media_item.get('user', {}).get('username', 'unknown')
            caption = media_item.get('caption', {}).get('text', '')
            
            # Create temp directory to store downloaded files
            download_dir = os.path.join(self.storage.get_temp_dir(), f"instagram_{shortcode}")
            os.makedirs(download_dir, exist_ok=True)
            
            # Download media files
            media_files = []
            
            if is_carousel:
                # Handle carousel/album
                carousel_media = media_item.get('carousel_media', [])
                for i, item in enumerate(carousel_media):
                    item_type = item.get('media_type', 1)
                    if item_type == 2 or 'video_versions' in item:  # Video
                        video_url = item.get('video_versions', [{}])[0].get('url')
                        if video_url:
                            file_path = os.path.join(download_dir, f"video_{i}.mp4")
                            self._download_file(video_url, file_path)
                            media_files.append(file_path)
                    else:  # Image
                        image_url = item.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
                        if image_url:
                            file_path = os.path.join(download_dir, f"image_{i}.jpg")
                            self._download_file(image_url, file_path)
                            media_files.append(file_path)
            elif is_video:
                # Handle video
                video_url = media_item.get('video_versions', [{}])[0].get('url')
                if video_url:
                    file_path = os.path.join(download_dir, "video.mp4")
                    self._download_file(video_url, file_path)
                    media_files.append(file_path)
            else:
                # Handle image
                image_url = media_item.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
                if image_url:
                    file_path = os.path.join(download_dir, "image.jpg")
                    self._download_file(image_url, file_path)
                    media_files.append(file_path)
            
            # Return post metadata
            return {
                'shortcode': shortcode,
                'media_id': media_item.get('id'),
                'username': username,
                'caption': caption,
                'media_files': media_files,
                'local_path': download_dir,
                'original_url': post_url,
                'type': 'carousel' if is_carousel else 'video' if is_video else 'image',
                'user_info': media_item.get('user', {})
            }
            
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
    
    def direct_repost(self, post_url: str, new_caption: str, instagram_username: str, instagram_password: str) -> Dict[str, Any]:
        """
        Directly repost an Instagram post without exposing download steps to the user.
        
        Args:
            post_url (str): URL of the Instagram post to repost
            new_caption (str): New caption for the repost
            instagram_username (str): Instagram username
            instagram_password (str): Instagram password
            
        Returns:
            dict: Result information
        """
        try:
            # Log the action
            logger.info(f"Direct repost initiated for URL: {post_url}")
            
            # Ensure we're logged in
            if not self.is_logged_in:
                self.login(instagram_username, instagram_password)
            
            # Extract shortcode from URL
            shortcode = self._extract_shortcode_from_url(post_url)
            logger.debug(f"Extracted shortcode for direct repost: {shortcode}")
            
            # Get post data directly from Instagram API
            try:
                # First try with our enhanced shortcode method
                media_info = self.get_media_info_by_shortcode(shortcode)
                
                # Extract necessary info
                items = media_info.get('items', [])
                if not items:
                    raise ValueError("Post not found or is private")
                
                item = items[0]
                
                # Get original caption if available and not overridden
                if not new_caption or new_caption.lower() == "original":
                    original_caption = item.get('caption', {}).get('text', '')
                    new_caption = original_caption or "Reposted with InstaBot"
                
                # Determine media type
                is_video = item.get('media_type') == 2 or bool(item.get('video_versions'))
                is_carousel = item.get('media_type') == 8 or bool(item.get('carousel_media'))
                
                # Create a temporary directory for downloads
                import tempfile
                import os
                import shutil
                temp_dir = tempfile.mkdtemp()
                
                try:
                    # Download media
                    media_files = []
                    
                    if is_carousel:
                        # Handle carousel/album
                        carousel_items = item.get('carousel_media', [])
                        for i, carousel_item in enumerate(carousel_items):
                            if carousel_item.get('media_type') == 2 or bool(carousel_item.get('video_versions')):
                                # Video in carousel
                                video_url = carousel_item.get('video_versions', [{}])[0].get('url')
                                if video_url:
                                    file_path = os.path.join(temp_dir, f"carousel_video_{i}.mp4")
                                    self._download_file(video_url, file_path)
                                    media_files.append(file_path)
                            else:
                                # Image in carousel
                                image_url = carousel_item.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
                                if image_url:
                                    file_path = os.path.join(temp_dir, f"carousel_image_{i}.jpg")
                                    self._download_file(image_url, file_path)
                                    media_files.append(file_path)
                    elif is_video:
                        # Handle video
                        video_url = item.get('video_versions', [{}])[0].get('url')
                        if video_url:
                            file_path = os.path.join(temp_dir, "video.mp4")
                            self._download_file(video_url, file_path)
                            media_files.append(file_path)
                    else:
                        # Handle image
                        image_url = item.get('image_versions2', {}).get('candidates', [{}])[0].get('url')
                        if image_url:
                            file_path = os.path.join(temp_dir, "image.jpg")
                            self._download_file(image_url, file_path)
                            media_files.append(file_path)
                    
                    if not media_files:
                        raise ValueError("Could not download any media from the post")
                    
                    # Post to Instagram
                    result = self.post_to_instagram(media_files, new_caption)
                    
                    # Return result
                    return {
                        "success": True if result else False,
                        "url": f"https://instagram.com/{self.username}",
                        "caption": new_caption
                    }
                    
                finally:
                    # Clean up temporary directory
                    try:
                        shutil.rmtree(temp_dir)
                        logger.debug("Cleaned up temporary files after direct repost")
                    except Exception as cleanup_error:
                        logger.error(f"Failed to clean up temporary files: {cleanup_error}")
                
            except Exception as api_error:
                logger.error(f"API error during direct repost: {api_error}")
                return {"success": False, "error": str(api_error)}
            
        except Exception as e:
            logger.error(f"Error in direct_repost: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
    
    def _download_file(self, url: str, file_path: str):
        """
        Download a file from a URL and save it to a local path.
        
        Args:
            url (str): URL of the file
            file_path (str): Local path to save the file
        """
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            logger.info(f"Downloaded file to {file_path}")
        else:
            raise Exception(f"Failed to download file: {response.status_code}")
