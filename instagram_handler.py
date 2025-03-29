import instaloader
import os
from typing import Dict, List, Any, Optional

class InstagramHandler:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern='',
            max_connection_attempts=3
        )
        
    def download_instagram_post(self, post_url: str, instagram_username: Optional[str] = None, instagram_password: Optional[str] = None) -> Dict[str, Any]:
        """Download an Instagram post and return its metadata."""
        try:
            # Validate URL format
            if 'instagram.com' not in post_url:
                raise ValueError("Invalid Instagram URL. Please provide a valid Instagram post URL.")
            
            # Clean up the URL - remove query parameters
            clean_url = post_url.split('?')[0].rstrip('/')
            
            # Extract shortcode from URL
            parts = clean_url.split('/')
            
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
            
            # Try to authenticate if credentials are provided
            if instagram_username and instagram_password:
                try:
                    self.loader.login(instagram_username, instagram_password)
                except instaloader.exceptions.InstaloaderException as e:
                    raise Exception(f"Login failed: {str(e)}")
            
            try:
                # Set modern user agent and additional headers
                self.loader.context._session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive'
                })
                
                # Set shorter timeouts
                self.loader.context._session.timeout = 10
                
                post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            except instaloader.exceptions.InstaloaderException as e:
                error_msg = str(e).lower()
                if 'login_required' in error_msg:
                    raise Exception("This post requires authentication")
                elif 'not found' in error_msg:
                    raise ValueError("Post not found. It might have been deleted or be private.")
                elif 'rate limit' in error_msg:
                    raise Exception("Instagram rate limit reached. Please try again later.")
                else:
                    raise Exception(f"Instagram error: {str(e)}")
            
            # Create a unique directory for this post
            target_dir = f"{post.owner_username}_{post.shortcode}"
            os.makedirs(target_dir, exist_ok=True)
            
            # Download the post
            self.loader.download_post(post, target=target_dir)
            
            # Get media files info
            media_files = []
            
            # List all downloaded files
            downloaded_files = [f for f in os.listdir(target_dir) if not f.endswith('.txt')]
            
            # Sort files to maintain order
            downloaded_files.sort()
            
            for file in downloaded_files:
                file_path = os.path.join(target_dir, file)
                media_type = 'video' if file.endswith('.mp4') else 'photo'
                
                media_files.append({
                    'type': media_type,
                    'path': file_path,
                    'url': post.video_url if media_type == 'video' else post.url
                })
            
            return {
                "username": post.owner_username,
                "caption": post.caption or "",
                "media_files": media_files,
                "download_path": target_dir,
                "shortcode": post.shortcode
            }
            
        except ValueError as e:
            # Re-raise validation errors as is
            raise
        except instaloader.exceptions.InstaloaderException as e:
            raise Exception(f"Instagram error: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to download post: {str(e)}")
