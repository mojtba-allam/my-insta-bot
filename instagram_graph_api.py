import os
import requests
from typing import Optional, Dict, Any

class InstagramGraphAPI:
    def __init__(self, access_token: str, instagram_account_id: str):
        self.access_token = access_token
        self.instagram_account_id = instagram_account_id
        self.api_version = 'v18.0'
        self.base_url = f'https://graph.facebook.com/{self.api_version}'
    
    def create_container(self, image_url: str, caption: str) -> Optional[str]:
        """Create a media container for the image."""
        url = f'{self.base_url}/{self.instagram_account_id}/media'
        
        params = {
            'image_url': image_url,
            'caption': caption,
            'access_token': self.access_token
        }
        
        response = requests.post(url, params=params)
        data = response.json()
        
        if 'id' in data:
            return data['id']
        elif 'error' in data:
            raise Exception(f"Failed to create container: {data['error']['message']}")
        return None
    
    def publish_container(self, creation_id: str) -> Optional[str]:
        """Publish a media container."""
        url = f'{self.base_url}/{self.instagram_account_id}/media_publish'
        
        params = {
            'creation_id': creation_id,
            'access_token': self.access_token
        }
        
        response = requests.post(url, params=params)
        data = response.json()
        
        if 'id' in data:
            return data['id']
        elif 'error' in data:
            raise Exception(f"Failed to publish: {data['error']['message']}")
        return None
    
    def post_to_instagram(self, image_url: str, caption: str) -> Dict[str, Any]:
        """Post content to Instagram using the Graph API."""
        try:
            # Step 1: Create a media container
            creation_id = self.create_container(image_url, caption)
            if not creation_id:
                raise Exception("Failed to create media container")
            
            # Step 2: Publish the container
            media_id = self.publish_container(creation_id)
            if not media_id:
                raise Exception("Failed to publish media")
            
            return {
                "success": True,
                "media_id": media_id,
                "post_url": f"https://www.instagram.com/p/{media_id}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
