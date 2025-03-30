"""
Combined Instagram client functionality.
This file merges mobile_instagram_client.py and robust_instagram_client.py.
"""
import os
import time
import random
import json
import pickle
import logging
import requests
from instagram_private_api import Client, ClientCompatPatch
from instagram_private_api.errors import ClientError, ClientLoginError

# Configure logging
logger = logging.getLogger(__name__)

class MobileInstagramClient:
    """
    Mobile Instagram client using the instagram_private_api.
    Handles login, session management, and content upload.
    """
    
    def __init__(self, proxy=None, storage_handler=None):
        """
        Initialize the client.
        
        Args:
            proxy (str, optional): Proxy URL for requests. Format: 'http://user:pass@ip:port'
            storage_handler: Storage handler for saving sessions (uses Google Drive if configured)
        """
        self.api = None
        self.is_logged_in = False
        self.username = None
        self.device_id = None
        self.proxy = proxy
        self.storage_handler = storage_handler
        
        # Create sessions directory if it doesn't exist (fallback only)
        os.makedirs("sessions", exist_ok=True)
    
    def _generate_device_id(self, username, password):
        """Generate a device ID based on username and password."""
        seed = f"{username}{password}{str(int(time.time()))}"
        m = random.randint(1, 1000)
        device_id = f"android-{m:x}{random.randint(1000, 9999):x}"
        return device_id
    
    def login(self, username, password, force_login=False):
        """
        Login to Instagram using the mobile API with session caching.
        """
        self.username = username
        session_file = f"sessions/{username.lower()}_mobile.pkl"
        
        # Try to reuse cached session if it exists and we're not forcing login
        cached_settings = None
        
        if not force_login:
            try:
                logger.info(f"Attempting to use cached session for {username}")
                
                # Try to get session from storage handler first (Google Drive)
                if self.storage_handler:
                    cached_settings = self.storage_handler.load_instagram_session(username)
                    if cached_settings:
                        logger.info(f"Loaded session from storage handler for {username}")
                
                # Fallback to local file if storage handler not available or session not found
                if not cached_settings and os.path.exists(session_file):
                    with open(session_file, "rb") as f:
                        cached_settings = pickle.load(f)
                    logger.info(f"Loaded session from local file for {username}")
                
                if cached_settings:
                    # Create client with cached settings
                    self.api = Client(
                        username,
                        password,
                        settings=cached_settings,
                    )
                    
                    # Verify connectivity with a basic request
                    try:
                        # Test connection with a lightweight API call
                        self.api.get_client_settings()
                        logger.info(f"Successfully logged in using cached session for {username}")
                        self.is_logged_in = True
                        return True
                    except Exception as conn_error:
                        if "temporary failure in name resolution" in str(conn_error).lower():
                            logger.error(f"Network connectivity issue detected: {str(conn_error)}")
                            raise Exception("network_error: Instagram servers cannot be reached. Check your internet connection and try again later.")
                        logger.warning(f"Cached session failed verification: {str(conn_error)}")
                        # Continue to fresh login
            except Exception as e:
                logger.warning(f"Failed to use cached session: {str(e)}")
                if os.path.exists(session_file):
                    os.remove(session_file)
        
        # Generate a device ID if we don't have one
        if not self.device_id:
            self.device_id = self._generate_device_id(username, password)
        
        # Try to login with multiple retries
        max_retries = 5
        device_configs = [
            {'manufacturer': 'Samsung', 'model': 'SM-G973F', 'android_release': '10', 'android_version': 29},
            {'manufacturer': 'Google', 'model': 'Pixel 4', 'android_release': '11', 'android_version': 30},
            {'manufacturer': 'OnePlus', 'model': 'OnePlus8Pro', 'android_release': '11', 'android_version': 30}
        ]
        
        for attempt in range(1, max_retries + 1):
            # Pick a device configuration based on attempt number
            device_config = device_configs[(attempt - 1) % len(device_configs)]
            
            try:
                logger.info(f"Login attempt {attempt}/{max_retries} for {username} with device: {device_config['manufacturer']} {device_config['model']}")
                
                # Create a new client and login
                self.api = Client(
                    username,
                    password,
                    device_id=self.device_id,
                    **device_config
                )
                
                # Check if login was successful by retrieving user info
                user_info = self.api.username_info(username)
                if user_info and 'user' in user_info:
                    logger.info(f"Successfully logged in as {username}")
                    
                    # Cache the session settings
                    if self.storage_handler:
                        # Save to Google Drive via storage handler
                        self.storage_handler.save_instagram_session(username, self.api.settings)
                        logger.info(f"Saved session to storage handler for {username}")
                    else:
                        # Fallback to local file if storage handler not available
                        with open(session_file, "wb") as f:
                            pickle.dump(self.api.settings, f)
                        logger.info(f"Saved session to local file for {username}")
                    
                    self.is_logged_in = True
                    return True
            
            except ClientLoginError as e:
                logger.error(f"Login error: {str(e)}")
                error_msg = str(e).lower()
                
                # Check for known error types
                if "challenge_required" in error_msg:
                    logger.error("Instagram security challenge required. Manual verification needed.")
                    raise
                elif "bad_password" in error_msg:
                    logger.error("Incorrect password provided.")
                    raise
                elif "invalid_user" in error_msg:
                    logger.error("Invalid username. The account may not exist or may have been deactivated.")
                    raise Exception("invalid_user")
                
                # For other errors, retry with delay if we have attempts left
                if attempt < max_retries:
                    sleep_time = 5 + random.uniform(1, 5)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed to login after {max_retries} attempts")
                    raise
            
            except Exception as e:
                logger.error(f"Unexpected error during login: {str(e)}")
                if attempt < max_retries:
                    sleep_time = 5 + random.uniform(1, 5)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed to login after {max_retries} attempts")
                    raise
        
        return False
    
    def upload_photo(self, photo_path, caption="", options=None):
        """
        Upload a photo to Instagram.
        
        Args:
            photo_path (str): Path to the photo file.
            caption (str, optional): Caption for the photo.
            options (dict, optional): Additional options for upload.
            
        Returns:
            dict: Response from Instagram API.
        """
        if not self.is_logged_in or not self.api:
            raise Exception("You must be logged in to upload photos")
        
        try:
            upload_options = {}
            if options:
                upload_options.update(options)
            
            logger.info(f"Uploading photo from {photo_path}")
            result = self.api.post_photo(
                photo_path, 
                caption=caption,
                **upload_options
            )
            
            # Log the result
            if result and isinstance(result, dict) and 'status' in result and result['status'] == 'ok':
                logger.info("Photo uploaded successfully to Instagram")
                return result
            else:
                logger.warning(f"Photo upload completed with unexpected response: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to upload photo: {str(e)}")
            raise
    
    def get_media_by_shortcode(self, shortcode):
        """
        Get media information using a shortcode.
        
        This is a wrapper around the private API to make it more accessible.
        
        Args:
            shortcode (str): Instagram post shortcode (from URL)
            
        Returns:
            dict: Media information or None
        """
        if not self.is_logged_in or not self.api:
            raise Exception("You must be logged in to get media information")
        
        try:
            # Some versions of the API have a direct media_info_by_code method
            try:
                return self.api.media_info_by_code(shortcode)
            except AttributeError:
                # Fall back to documented method
                pass
            
            # Use the documented endpoint
            try:
                # Try to use the direct media info endpoint
                return self.api.media_info2(shortcode)
            except (AttributeError, Exception) as e:
                logger.debug(f"Error with media_info2: {e}")
            
            # Try to fetch user feed and search for the post
            # First get the information directly using Instagram's web API
            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            url = f'https://www.instagram.com/p/{shortcode}/'
            
            try:
                resp = requests.get(url, headers=headers)
                
                # Search for JSON data in the response
                import re
                import json
                json_data = re.search(r'<script[^>]*>window\._sharedData\s*=\s*(.*?);</script>', resp.text)
                if json_data:
                    data = json.loads(json_data.group(1))
                    media_data = data.get('entry_data', {}).get('PostPage', [{}])[0].get('graphql', {}).get('shortcode_media', {})
                    
                    if media_data:
                        # Convert to format similar to API response
                        return {
                            'items': [{
                                'id': media_data.get('id'),
                                'media_type': 1 if media_data.get('__typename') == 'GraphImage' else 2,
                                'image_versions2': {
                                    'candidates': [{'url': media_data.get('display_url')}]
                                },
                                'video_versions': [{'url': media_data.get('video_url')}] if media_data.get('is_video') else [],
                                'user': {
                                    'username': media_data.get('owner', {}).get('username'),
                                    'full_name': media_data.get('owner', {}).get('full_name'),
                                },
                                'caption': {'text': media_data.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', '')},
                                'like_count': media_data.get('edge_media_preview_like', {}).get('count', 0),
                                'comment_count': media_data.get('edge_media_to_comment', {}).get('count', 0),
                                'taken_at': media_data.get('taken_at_timestamp', 0)
                            }]
                        }
            except Exception as web_error:
                logger.error(f"Error fetching media from web API: {web_error}")
            
            # Try one more approach - this is a fallback that might work with some API versions
            endpoint = f'media/{shortcode}/info/'
            return self.api._call_api(endpoint)
        
        except Exception as e:
            logger.error(f"Error in get_media_by_shortcode: {str(e)}")
            raise
    
    def logout(self):
        """Logout from Instagram."""
        if self.api and self.is_logged_in:
            try:
                self.api.logout()
                logger.info(f"Logged out from Instagram: {self.username}")
                self.is_logged_in = False
                self.username = None
                return True
            except Exception as e:
                logger.error(f"Error logging out: {str(e)}")
                return False
        return True
