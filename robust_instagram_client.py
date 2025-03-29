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
        
        # Check for proxy in environment variables
        proxy = os.getenv("INSTAGRAM_PROXY")
        if proxy:
            logger.info(f"Using proxy: {proxy}")
            self.set_proxy(proxy)
    
    def robust_login(self, username, password, force_login=False, use_proxy=None):
        """Login to Instagram with retries and session handling."""
        self.session_file = f"sessions/{username.lower()}.json"
        
        # Set proxy if provided directly
        if use_proxy:
            logger.info(f"Setting proxy for login: {use_proxy}")
            self.set_proxy(use_proxy)
        
        if not force_login and os.path.exists(self.session_file) and self._try_load_session(username, password):
            logger.info(f"Successfully logged in using saved session for {username}")
            return True
        
        # Fresh login with multiple retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Login attempt {attempt}/{self.max_retries} for {username}")
                
                # Randomize some settings to appear more human-like
                self.delay_range = [random.uniform(2.5, 4), random.uniform(5, 7)]
                
                # Try different user agents on retry
                if attempt > 1:
                    user_agents = [
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
                    ]
                    self.user_agent = random.choice(user_agents)
                    logger.info(f"Using user agent: {self.user_agent}")
                
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
                
                # Try with a proxy on subsequent attempts if we're on Render
                if attempt == 2 and os.getenv('RENDER', 'false').lower() == 'true':
                    free_proxy = self._get_free_proxy()
                    if free_proxy:
                        logger.info(f"Trying with free proxy: {free_proxy}")
                        self.set_proxy(free_proxy)
                
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
    
    def _get_free_proxy(self):
        """Get a free proxy to try"""
        try:
            import requests
            # Try to get a free proxy from a public API
            response = requests.get('https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all', timeout=10)
            if response.status_code == 200:
                proxies = response.text.strip().split('\n')
                if proxies:
                    # Format: ip:port
                    return f"http://{random.choice(proxies)}"
        except Exception as e:
            logger.error(f"Error getting free proxy: {str(e)}")
        return None
