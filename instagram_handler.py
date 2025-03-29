import os
import tempfile
from typing import Dict, List, Any, Optional
from instagrapi import Client
from urllib.parse import urlparse
import shutil

class InstagramHandler:
    def __init__(self):
        self.client = None
        self.temp_dir = tempfile.mkdtemp()
        
    def download_instagram_post(self, post_url: str, instagram_username: Optional[str] = None, instagram_password: Optional[str] = None) -> Dict[str, Any]:
        """Download an Instagram post and return its metadata."""
        try:
            # Validate URL format
            if 'instagram.com' not in post_url:
                raise ValueError("Invalid Instagram URL. Please provide a valid Instagram post URL.")
            
            # Clean up the URL - remove query parameters
            clean_url = post_url.split('?')[0].rstrip('/')
            
            # Extract media ID from URL
            parts = clean_url.split('/')
            media_pk = None
            
            # Find the shortcode after 'p' or 'reel'
            shortcode = None
            for i, part in enumerate(parts):
                if part in ['p', 'reel'] and i + 1 < len(parts):
                    shortcode = parts[i + 1]
                    break
            
            if not shortcode:
                raise ValueError(
                    "Could not find post ID in the URL. \n"
                    "The URL should be in one of these formats:\n"
                    "- instagram.com/p/POSTID\n"
                    "- instagram.com/reel/POSTID"
                )
            
            # Initialize client and login if needed
            if not self.client:
                self.client = Client()
                if instagram_username and instagram_password:
                    try:
                        self.client.login(instagram_username, instagram_password)
                    except Exception as e:
                        raise Exception(f"Login failed: {str(e)}")
            
            try:
                # Get media ID from shortcode
                media_pk = self.client.media_pk_from_code(shortcode)
                
                # Get media info
                media_info = self.client.media_info(media_pk)
                
                # Create a unique directory for this post inside temp_dir
                target_dir = os.path.join(self.temp_dir, f"{media_info.user.username}_{shortcode}")
                os.makedirs(target_dir, exist_ok=True)
                
                media_files = []
                
                # Handle different media types
                if media_info.media_type == 1:  # Photo
                    file_path = os.path.join(target_dir, f"{shortcode}.jpg")
                    # Download to the directory, not directly to the file path
                    downloaded_path = self.client.photo_download(media_pk, target_dir)
                    # Convert PosixPath to string if needed
                    downloaded_path = str(downloaded_path) if downloaded_path else None
                    # If downloaded path exists, use it, otherwise use our created path
                    if downloaded_path and os.path.exists(downloaded_path):
                        file_path = downloaded_path
                    media_files.append({
                        'type': 'photo',
                        'path': file_path,
                        'url': media_info.thumbnail_url
                    })
                elif media_info.media_type == 2:  # Video
                    file_path = os.path.join(target_dir, f"{shortcode}.mp4")
                    # Download to the directory, not directly to the file path
                    downloaded_path = self.client.video_download(media_pk, target_dir)
                    # Convert PosixPath to string if needed
                    downloaded_path = str(downloaded_path) if downloaded_path else None
                    # If downloaded path exists, use it, otherwise use our created path
                    if downloaded_path and os.path.exists(downloaded_path):
                        file_path = downloaded_path
                    media_files.append({
                        'type': 'video',
                        'path': file_path,
                        'url': media_info.video_url
                    })
                elif media_info.media_type == 8:  # Album
                    for i, resource in enumerate(media_info.resources):
                        if resource.media_type == 1:  # Photo in album
                            file_path = os.path.join(target_dir, f"{shortcode}_{i}.jpg")
                            # Download to the directory, not directly to the file path
                            downloaded_path = self.client.photo_download(resource.pk, target_dir)
                            # Convert PosixPath to string if needed
                            downloaded_path = str(downloaded_path) if downloaded_path else None
                            # If downloaded path exists, use it, otherwise use our created path
                            if downloaded_path and os.path.exists(downloaded_path):
                                file_path = downloaded_path
                            media_files.append({
                                'type': 'photo',
                                'path': file_path,
                                'url': resource.thumbnail_url
                            })
                        elif resource.media_type == 2:  # Video in album
                            file_path = os.path.join(target_dir, f"{shortcode}_{i}.mp4")
                            # Download to the directory, not directly to the file path
                            downloaded_path = self.client.video_download(resource.pk, target_dir)
                            # Convert PosixPath to string if needed
                            downloaded_path = str(downloaded_path) if downloaded_path else None
                            # If downloaded path exists, use it, otherwise use our created path
                            if downloaded_path and os.path.exists(downloaded_path):
                                file_path = downloaded_path
                            media_files.append({
                                'type': 'video',
                                'path': file_path,
                                'url': resource.video_url
                            })
                
                return {
                    "username": media_info.user.username,
                    "caption": media_info.caption_text or "",
                    "media_files": media_files,
                    "download_path": target_dir,
                    "shortcode": shortcode
                }
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'login_required' in error_msg:
                    raise Exception("This post requires authentication")
                elif 'not found' in error_msg:
                    raise ValueError("Post not found. It might have been deleted or be private.")
                elif 'rate limit' in error_msg:
                    raise Exception("Instagram rate limit reached. Please try again later.")
                else:
                    raise Exception(f"Instagram error: {str(e)}")
                    
        except ValueError as e:
            # Re-raise validation errors as is
            raise
        except Exception as e:
            raise Exception(f"Failed to download post: {str(e)}")
            
    def cleanup(self):
        """Clean up temporary files and logout."""
        try:
            if self.client:
                self.client.logout()
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass  # Best effort cleanup
