import os
import json
import time
import random
import logging
import pickle
from instagram_private_api import Client, ClientCompatPatch
from instagram_private_api.errors import ClientError, ClientLoginError

logger = logging.getLogger(__name__)

class MobileInstagramClient:
    """
    A mobile-focused Instagram client that uses the official Instagram private API
    to emulate the behavior of the official Instagram app.
    """
    
    def __init__(self):
        self.api = None
        self.username = None
        self.device_id = None
        self.is_logged_in = False
        
        # Create sessions directory if it doesn't exist
        os.makedirs("sessions", exist_ok=True)
    
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
                logger.info(f"Successfully logged in using cached session for {username}")
                self.is_logged_in = True
                return True
            except Exception as e:
                logger.warning(f"Failed to use cached session: {str(e)}")
                if os.path.exists(session_file):
                    os.remove(session_file)
        
        # Generate a device ID if we don't have one
        if not self.device_id:
            self.device_id = self._generate_device_id(username, password)
        
        # Try to login with multiple retries
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Login attempt {attempt}/{max_retries} for {username}")
                
                # Set custom device info for each attempt
                # Using a mix of device settings to appear as a real mobile device
                if attempt > 1:
                    device_info = random.choice([
                        {'manufacturer': 'Samsung', 'model': 'SM-G973F', 'android_release': '10', 'android_version': 29},
                        {'manufacturer': 'Google', 'model': 'Pixel 4', 'android_release': '11', 'android_version': 30},
                        {'manufacturer': 'OnePlus', 'model': 'OnePlus8Pro', 'android_release': '11', 'android_version': 30}
                    ])
                else:
                    device_info = {'manufacturer': 'Samsung', 'model': 'SM-G973F', 'android_release': '10', 'android_version': 29}
                
                # Create a new client and login
                self.api = Client(
                    username,
                    password,
                    device_id=self.device_id,
                    **device_info
                )
                
                # Check if login was successful
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
                
                # For other errors, retry with delay
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
    
    def upload_photo(self, photo_path, caption="", location=None):
        """
        Upload a photo to Instagram.
        """
        if not self.is_logged_in or not self.api:
            raise Exception("Not logged in")
        
        try:
            logger.info(f"Uploading photo: {photo_path}")
            
            # Add some randomized delays to mimic human behavior
            time.sleep(random.uniform(1, 3))
            
            # Upload the photo
            result = self.api.post_photo(
                photo_path,
                caption=caption,
                location=location
            )
            
            # Extract media ID and code from result
            media_id = result.get('media', {}).get('id')
            media_code = result.get('media', {}).get('code')
            
            logger.info(f"Successfully uploaded photo. Media ID: {media_id}, Code: {media_code}")
            return {
                'media_id': media_id,
                'media_code': media_code,
                'status': 'success'
            }
        
        except Exception as e:
            logger.error(f"Error uploading photo: {str(e)}")
            raise
    
    def upload_video(self, video_path, thumbnail_path, caption="", location=None):
        """
        Upload a video to Instagram.
        """
        if not self.is_logged_in or not self.api:
            raise Exception("Not logged in")
        
        try:
            logger.info(f"Uploading video: {video_path}")
            
            # Add some randomized delays to mimic human behavior
            time.sleep(random.uniform(2, 5))
            
            # Upload the video
            result = self.api.post_video(
                video_path,
                thumbnail_path,
                caption=caption,
                location=location
            )
            
            # Extract media ID and code from result
            media_id = result.get('media', {}).get('id')
            media_code = result.get('media', {}).get('code')
            
            logger.info(f"Successfully uploaded video. Media ID: {media_id}, Code: {media_code}")
            return {
                'media_id': media_id,
                'media_code': media_code,
                'status': 'success'
            }
        
        except Exception as e:
            logger.error(f"Error uploading video: {str(e)}")
            raise
    
    def logout(self):
        """
        Logout from Instagram.
        """
        if self.api:
            try:
                self.api.logout()
                logger.info(f"Logged out from Instagram: {self.username}")
            except:
                pass
            
            self.api = None
            self.is_logged_in = False
    
    def _generate_device_id(self, username, password):
        """
        Generate a unique device ID based on username and password.
        """
        seed = f"{username}{password}{''.join(str(random.randint(0, 9)) for _ in range(4))}"
        m = random.randint(1, 1000)
        device_id = f"android-{m:x}{random.randint(1000, 9999):x}"
        return device_id
