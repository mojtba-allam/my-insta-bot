import os
import json
import logging
from typing import Dict, Any, List, Optional

# Import the Google Drive handler
from google_drive_handler import GoogleDriveHandler

logger = logging.getLogger(__name__)

class StorageHandler:
    """Handle storage for user credentials and media files."""
    
    def __init__(self, data_dir="data", use_google_drive=False, credentials_file="credentials.json"):
        """Initialize the storage handler.
        
        Args:
            data_dir: Directory to store local data
            use_google_drive: Whether to use Google Drive for storage
            credentials_file: Path to Google API credentials file
        """
        self.data_dir = data_dir
        self.credentials_file = os.path.abspath(credentials_file)
        self.use_google_drive = use_google_drive
        self.google_drive = None
        
        # Create local data directory if it doesn't exist
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        # Initialize Google Drive if enabled
        if use_google_drive:
            try:
                self.google_drive = GoogleDriveHandler(
                    credentials_file=credentials_file,
                    token_file=os.path.join(data_dir, "token.json"),
                    folder_name="Instagram_Bot_Data"
                )
                logger.info("Successfully initialized Google Drive storage")
            except Exception as e:
                logger.error(f"Failed to initialize Google Drive storage: {str(e)}")
                logger.info("Falling back to local storage")
    
    def save_credentials(self, user_id: int, username: str, password: str) -> bool:
        """Save Instagram credentials for a user.
        
        Args:
            user_id: Telegram user ID
            username: Instagram username
            password: Instagram password
            
        Returns:
            bool: True if save was successful
        """
        # Always save locally first
        user_dir = os.path.join(self.data_dir, str(user_id))
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
            
        credentials = {
            "user_id": user_id,
            "username": username,
            "password": password
        }
        
        local_path = os.path.join(user_dir, "credentials.json")
        try:
            with open(local_path, 'w') as f:
                json.dump(credentials, f)
            logger.info(f"Saved credentials locally for user {user_id}")
            
            # Save to Google Drive if enabled
            if self.use_google_drive and self.google_drive:
                try:
                    result = self.google_drive.save_instagram_data(user_id, username, password)
                    logger.info(f"Saved credentials to Google Drive for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to save credentials to Google Drive: {str(e)}")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {str(e)}")
            return False
    
    def load_credentials(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Load Instagram credentials for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            dict or None: Credentials if found, None otherwise
        """
        # Try Google Drive first if enabled
        if self.use_google_drive and self.google_drive:
            try:
                credentials = self.google_drive.load_user_credentials(user_id)
                if credentials:
                    logger.info(f"Loaded credentials from Google Drive for user {user_id}")
                    return credentials
            except Exception as e:
                logger.error(f"Failed to load credentials from Google Drive: {str(e)}")
        
        # Fall back to local storage
        user_dir = os.path.join(self.data_dir, str(user_id))
        creds_path = os.path.join(user_dir, "credentials.json")
        
        if os.path.exists(creds_path):
            try:
                with open(creds_path, 'r') as f:
                    credentials = json.load(f)
                logger.info(f"Loaded credentials locally for user {user_id}")
                return credentials
            except Exception as e:
                logger.error(f"Failed to load credentials: {str(e)}")
        
        return None
    
    def load_all_credentials(self) -> List[Dict[str, Any]]:
        """Load all stored Instagram credentials.
        
        Returns:
            list: List of credential dictionaries
        """
        all_credentials = []
        
        # Try Google Drive first if enabled
        if self.use_google_drive and self.google_drive:
            try:
                drive_credentials = self.google_drive.load_all_credentials()
                if drive_credentials:
                    all_credentials.extend(drive_credentials)
                    logger.info(f"Loaded {len(drive_credentials)} credential sets from Google Drive")
            except Exception as e:
                logger.error(f"Failed to load credentials from Google Drive: {str(e)}")
        
        # Also check local storage
        try:
            # Get all user directories
            for user_dir in os.listdir(self.data_dir):
                user_path = os.path.join(self.data_dir, user_dir)
                if os.path.isdir(user_path):
                    creds_path = os.path.join(user_path, "credentials.json")
                    if os.path.exists(creds_path):
                        try:
                            with open(creds_path, 'r') as f:
                                credentials = json.load(f)
                                # Only add if not already in list
                                if not any(c.get("user_id") == credentials.get("user_id") for c in all_credentials):
                                    all_credentials.append(credentials)
                        except Exception as e:
                            logger.error(f"Failed to load credentials for {user_dir}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to load local credentials: {str(e)}")
            
        return all_credentials
    
    def save_media(self, user_id: int, media_path: str) -> str:
        """Save media file and return the path where it was saved.
        
        Args:
            user_id: Telegram user ID
            media_path: Path to the media file
            
        Returns:
            str: Path where the media was saved
        """
        if not os.path.exists(media_path):
            raise FileNotFoundError(f"Media file not found: {media_path}")
            
        # Save locally
        user_dir = os.path.join(self.data_dir, str(user_id), "media")
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
            
        filename = os.path.basename(media_path)
        saved_path = os.path.join(user_dir, filename)
        
        # Copy the file
        import shutil
        shutil.copy2(media_path, saved_path)
        
        # Upload to Google Drive if enabled
        if self.use_google_drive and self.google_drive:
            try:
                folder_name = f"user_{user_id}"
                file_id = self.google_drive.upload_file(saved_path, folder_name)
                logger.info(f"Uploaded media to Google Drive for user {user_id}: {file_id}")
            except Exception as e:
                logger.error(f"Failed to upload media to Google Drive: {str(e)}")
                
        return saved_path
    
    def delete_user_data(self, user_id: int) -> bool:
        """Delete all data for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            bool: True if deletion was successful
        """
        success = True
        
        # Delete local data
        user_dir = os.path.join(self.data_dir, str(user_id))
        if os.path.exists(user_dir):
            try:
                import shutil
                shutil.rmtree(user_dir)
                logger.info(f"Deleted local data for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete local data for user {user_id}: {str(e)}")
                success = False
                
        # Delete from Google Drive if enabled
        if self.use_google_drive and self.google_drive:
            try:
                # Find user folder
                folder_name = f"user_{user_id}"
                query = f"name='{folder_name}' and '{self.google_drive.root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
                
                results = self.google_drive.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id, name)'
                ).execute()
                
                folders = results.get('files', [])
                
                if folders:
                    folder_id = folders[0]['id']
                    self.google_drive.service.files().delete(fileId=folder_id).execute()
                    logger.info(f"Deleted Google Drive data for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete Google Drive data for user {user_id}: {str(e)}")
                success = False
                
        return success
    
    def save_instagram_session(self, username, session_data):
        """
        Save Instagram session data to storage.
        
        Args:
            username: Instagram username
            session_data: Serializable session data
        
        Returns:
            bool: Success or failure
        """
        try:
            if not username:
                logger.error("Cannot save session with empty username")
                return False
                
            # Pickle the session data
            import pickle
            session_bytes = pickle.dumps(session_data)
            
            file_name = f"{username.lower()}_session.pkl"
            file_path = os.path.join(self.data_dir, file_name)
            
            if self.use_google_drive:
                # Save to Google Drive
                logger.info(f"Saving Instagram session for {username} to Google Drive")
                self.google_drive.upload_file_data(
                    file_name=file_name,
                    file_data=session_bytes, 
                    mime_type="application/octet-stream"
                )
            else:
                # Save locally
                logger.info(f"Saving Instagram session for {username} locally")
                # Ensure directory exists
                os.makedirs(self.data_dir, exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(session_bytes)
                    
            return True
        except Exception as e:
            logger.error(f"Error saving Instagram session: {str(e)}")
            return False
    
    def load_instagram_session(self, username):
        """
        Load Instagram session data from storage.
        
        Args:
            username: Instagram username
        
        Returns:
            object: Session data or None if not found
        """
        try:
            if not username:
                logger.error("Cannot load session with empty username")
                return None
                
            file_name = f"{username.lower()}_session.pkl"
            file_path = os.path.join(self.data_dir, file_name)
            
            session_bytes = None
            
            if self.use_google_drive:
                # Load from Google Drive
                logger.info(f"Loading Instagram session for {username} from Google Drive")
                session_bytes = self.google_drive.download_file_by_name(file_name)
            elif os.path.exists(file_path):
                # Load locally
                logger.info(f"Loading Instagram session for {username} locally")
                with open(file_path, 'rb') as f:
                    session_bytes = f.read()
            
            if session_bytes:
                # Unpickle the session data
                import pickle
                return pickle.loads(session_bytes)
                
            return None
        except Exception as e:
            logger.error(f"Error loading Instagram session: {str(e)}")
            return None
