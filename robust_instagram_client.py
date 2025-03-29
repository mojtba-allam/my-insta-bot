import os
import time
import random
import json
import logging
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

logger = logging.getLogger(__name__)

class RobustInstagramClient(Client):
    """A more robust Instagram client that can handle connection issues."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = 5
        self.retry_delay = 5
        self.session_file = None
        
        # Default sensible settings
        self.delay_range = [3, 7]
        self.request_timeout = 90
        
        # More realistic user agent
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        
        # Create sessions directory if it doesn't exist
        os.makedirs("sessions", exist_ok=True)
    
    def robust_login(self, username, password, force_login=False):
        """Login to Instagram with retries and session handling."""
        self.session_file = f"sessions/{username.lower()}.json"
        
        if not force_login and os.path.exists(self.session_file) and self._try_load_session(username, password):
            logger.info(f"Successfully logged in using saved session for {username}")
            return True
        
        # Fresh login with multiple retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Login attempt {attempt}/{self.max_retries} for {username}")
                
                # Randomize some settings to appear more human-like
                self.delay_range = [random.uniform(2.5, 4), random.uniform(5, 7)]
                
                # Set some request timeouts to avoid hanging
                # Do actual login
                super().login(username, password)
                
                # Save the session for future use
                self._save_session()
                logger.info(f"Login successful for {username}")
                return True
                
            except Exception as e:
                logger.error(f"Login attempt {attempt} failed: {str(e)}")
                if "challenge_required" in str(e).lower():
                    logger.error("Instagram security challenge detected. Manual verification may be required.")
                    raise
                
                # Add random delay before retrying
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay + random.uniform(1, 3)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All {self.max_retries} login attempts failed.")
                    raise
        
        return False
    
    def _try_load_session(self, username, password):
        """Try to load and use a saved session."""
        try:
            if not os.path.exists(self.session_file):
                return False
                
            logger.info(f"Loading session from {self.session_file}")
            with open(self.session_file, "r") as f:
                session_data = json.load(f)
                
            # Set session data
            self.set_settings(session_data)
            
            # Test if the session is valid
            try:
                self.get_timeline_feed()
                return True
            except LoginRequired:
                logger.warning("Session expired, need to login again")
                return False
                
        except Exception as e:
            logger.error(f"Error loading session: {str(e)}")
            return False
    
    def _save_session(self):
        """Save the current session for future use."""
        if not self.session_file:
            return
            
        try:
            session_data = self.get_settings()
            
            # Save session data to file
            with open(self.session_file, "w") as f:
                json.dump(session_data, f)
                
            logger.info(f"Session saved to {self.session_file}")
        except Exception as e:
            logger.error(f"Error saving session: {str(e)}")
