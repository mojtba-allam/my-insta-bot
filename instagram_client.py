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
    
    def __init__(self, proxy=None):
        """
        Initialize the client.
        
        Args:
            proxy (str, optional): Proxy URL for requests. Format: 'http://user:pass@ip:port'
        """
        self.api = None
        self.is_logged_in = False
        self.username = None
        self.device_id = None
        self.proxy = proxy
        
        # Create sessions directory if it doesn't exist
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
        if not force_login and os.path.exists(session_file):
            try:
                logger.info(f"Attempting to use cached session for {username}")
                with open(session_file, "rb") as f:
                    cached_settings = pickle.load(f)
                
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
                    with open(session_file, "wb") as f:
                        pickle.dump(self.api.settings, f)
                    
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
