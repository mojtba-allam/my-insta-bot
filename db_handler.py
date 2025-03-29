import os
from typing import Dict, Optional
from datetime import datetime

class DBHandler:
    def __init__(self):
        # This will be replaced with MongoDB connection later
        self.users = {}
        
    def save_user_credentials(self, user_id: int, instagram_username: str, instagram_password: str) -> None:
        """Save user's Instagram credentials (encrypted)."""
        # TODO: Implement proper encryption
        self.users[user_id] = {
            'instagram_username': instagram_username,
            'instagram_password': instagram_password,
            'updated_at': datetime.now()
        }
        
    def get_user_credentials(self, user_id: int) -> Optional[Dict]:
        """Get user's Instagram credentials."""
        return self.users.get(user_id)
        
    def delete_user_credentials(self, user_id: int) -> None:
        """Delete user's Instagram credentials."""
        if user_id in self.users:
            del self.users[user_id]
