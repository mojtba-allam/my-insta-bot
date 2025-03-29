import json
import os
from typing import Dict, List, Optional
from datetime import datetime

class StorageHandler:
    def __init__(self):
        self.data_dir = "data"
        self.credentials_file = os.path.join(self.data_dir, "credentials.json")
        self.posts_file = os.path.join(self.data_dir, "posts.json")
        self.media_dir = os.path.join(self.data_dir, "media")
        
        # Create directories if they don't exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)
        
        # Initialize storage files
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage files if they don't exist."""
        if not os.path.exists(self.credentials_file):
            self._save_json(self.credentials_file, {})
        if not os.path.exists(self.posts_file):
            self._save_json(self.posts_file, {})
    
    def _load_json(self, file_path: str) -> dict:
        """Load JSON data from file."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _save_json(self, file_path: str, data: dict):
        """Save data to JSON file."""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_credentials(self, user_id: int, username: str, password: str) -> bool:
        """Save user credentials."""
        data = self._load_json(self.credentials_file)
        data[str(user_id)] = {
            'username': username,
            'password': password,
            'updated_at': datetime.now().isoformat()
        }
        self._save_json(self.credentials_file, data)
        return True
    
    def get_credentials(self, user_id: int) -> Optional[Dict]:
        """Get user credentials."""
        data = self._load_json(self.credentials_file)
        return data.get(str(user_id))
    
    def save_media_file(self, file_path: str, media_type: str) -> str:
        """Save media file and return file ID."""
        # Generate unique filename
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(file_path)}"
        target_path = os.path.join(self.media_dir, filename)
        
        # Copy file to media directory
        with open(file_path, 'rb') as src, open(target_path, 'wb') as dst:
            dst.write(src.read())
        
        return filename
    
    def save_post_data(self, user_id: int, post_data: Dict, file_ids: List[str]) -> bool:
        """Save post data."""
        data = self._load_json(self.posts_file)
        
        if str(user_id) not in data:
            data[str(user_id)] = []
        
        post_info = {
            'post_data': post_data,
            'file_ids': file_ids,
            'created_at': datetime.now().isoformat()
        }
        
        data[str(user_id)].append(post_info)
        self._save_json(self.posts_file, data)
        return True
