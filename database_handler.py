import os
import json
from pymongo import MongoClient
from datetime import datetime
from pathlib import Path
from bson.binary import Binary
from typing import Optional, Dict, Any, Tuple

class DatabaseHandler:
    def __init__(self):
        # MongoDB connection
        mongo_uri = os.getenv('MONGODB_URI')
        if not mongo_uri:
            raise ValueError("MONGODB_URI environment variable not set")
            
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client['insta_bot']
        self.credentials = self.db['credentials']
        self.files = self.db['files']
        self.posts = self.db['posts']
        
    def save_credentials(self, user_id: int, username: str, password: str) -> bool:
        """Save Instagram credentials for a user"""
        try:
            self.credentials.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'username': username,
                        'password': password,
                        'updated_at': datetime.utcnow(),
                        'active': True
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error saving credentials: {e}")
            return False
        
    def get_credentials(self, user_id: int) -> Optional[Dict[str, str]]:
        """Retrieve Instagram credentials for a user"""
        creds = self.credentials.find_one({'user_id': user_id, 'active': True})
        if creds:
            return {
                'username': creds['username'],
                'password': creds['password']
            }
        return None
        
    def save_media_file(self, file_path: str, media_type: str) -> Optional[str]:
        """Save media file to MongoDB"""
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
                file_id = self.files.insert_one({
                    'data': Binary(file_data),
                    'type': media_type,
                    'created_at': datetime.utcnow()
                }).inserted_id
                return str(file_id)
        except Exception as e:
            print(f"Error saving file: {e}")
            return None

    def get_media_file(self, file_id: str) -> Optional[bytes]:
        """Get media file from MongoDB"""
        file_doc = self.files.find_one({'_id': file_id})
        if file_doc:
            return file_doc['data']
        return None

    def save_post_data(self, user_id: int, post_data: Dict[str, Any], file_ids: list) -> bool:
        """Save post data and associated files to MongoDB"""
        try:
            self.posts.insert_one({
                'user_id': user_id,
                'original_username': post_data.get('username'),
                'caption': post_data.get('caption'),
                'file_ids': file_ids,
                'created_at': datetime.utcnow()
            })
            return True
        except Exception as e:
            print(f"Error saving post data: {e}")
            return False
        cache_file = self.cache_dir / f"{hash(post_url)}.json"
        if not cache_file.exists():
            return None
            
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
            
        if datetime.utcnow().timestamp() > cache_data['expires_at']:
            cache_file.unlink()  # Delete expired cache
            return None
            
        return cache_data['data']
