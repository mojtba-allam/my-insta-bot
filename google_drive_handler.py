import os
import io
import json
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

class GoogleDriveHandler:
    """Handler for Google Drive operations."""
    
    # If modifying these scopes, delete the token.json file.
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self, credentials_file='credentials.json', token_file='token.json', folder_name='Instagram_Bot_Data'):
        """Initialize the Google Drive handler.
        
        Args:
            credentials_file: Path to the credentials.json file
            token_file: Path to the token.json file (will be created if it doesn't exist)
            folder_name: Name of the folder in Google Drive to store bot data
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.folder_name = folder_name
        self.service = None
        self.root_folder_id = None
        
        # Initialize the Google Drive API service
        self._authenticate()
        
        # Create or get the root folder
        self.root_folder_id = self._get_or_create_folder(self.folder_name)
        logger.info(f"Root folder ID: {self.root_folder_id}")
    
    def _authenticate(self):
        """Authenticate with Google Drive API."""
        creds = None
        
        # Load existing token if it exists
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_info(
                    json.load(open(self.token_file)),
                    self.SCOPES
                )
            except Exception as e:
                logger.error(f"Error loading token: {str(e)}")
        
        # If credentials don't exist or are invalid, run the OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file not found at {self.credentials_file}. "
                        "Please download credentials.json from Google Cloud Console."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        # Build the service
        self.service = build('drive', 'v3', credentials=creds)
    
    def _get_or_create_folder(self, folder_name, parent_id=None):
        """Get or create a folder in Google Drive.
        
        Args:
            folder_name: Name of the folder
            parent_id: ID of the parent folder (if None, use root)
            
        Returns:
            folder_id: ID of the folder
        """
        # First, try to find an existing folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        query += " and trashed=false"
        
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        
        # If folder exists, return its ID
        if items:
            return items[0]['id']
        
        # If folder doesn't exist, create it
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_id:
            folder_metadata['parents'] = [parent_id]
        
        folder = self.service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()
        
        return folder.get('id')
    
    def upload_file(self, file_path, folder_name=None):
        """Upload a file to Google Drive.
        
        Args:
            file_path: Path to the file to upload
            folder_name: Name of the subfolder (if None, use root folder)
            
        Returns:
            file_id: ID of the uploaded file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Determine parent folder ID
        parent_id = self.root_folder_id
        if folder_name:
            parent_id = self._get_or_create_folder(folder_name, self.root_folder_id)
        
        # Prepare file metadata and media
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }
        
        media = MediaFileUpload(
            file_path,
            resumable=True
        )
        
        # Upload the file
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        logger.info(f"Uploaded file: {file_name} (ID: {file.get('id')})")
        return file.get('id')
    
    def download_file(self, file_id, output_path):
        """Download a file from Google Drive.
        
        Args:
            file_id: ID of the file to download
            output_path: Path where to save the downloaded file
            
        Returns:
            bool: True if download was successful
        """
        try:
            # Get file metadata to check if it exists
            file_metadata = self.service.files().get(fileId=file_id).execute()
            
            # Download the file
            request = self.service.files().get_media(fileId=file_id)
            fh = io.FileIO(output_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Download {int(status.progress() * 100)}%")
            
            logger.info(f"Downloaded file: {file_metadata.get('name')} to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading file (ID: {file_id}): {str(e)}")
            return False
    
    def list_files(self, folder_name=None):
        """List files in a folder.
        
        Args:
            folder_name: Name of the subfolder (if None, use root folder)
            
        Returns:
            list: List of file metadata dicts (id, name)
        """
        # Determine parent folder ID
        folder_id = self.root_folder_id
        if folder_name:
            folder_id = self._get_or_create_folder(folder_name, self.root_folder_id)
        
        # Query files in the folder
        query = f"'{folder_id}' in parents and trashed=false"
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType)'
        ).execute()
        
        items = results.get('files', [])
        return items
    
    def delete_file(self, file_id):
        """Delete a file from Google Drive.
        
        Args:
            file_id: ID of the file to delete
            
        Returns:
            bool: True if deletion was successful
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file with ID: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file (ID: {file_id}): {str(e)}")
            return False
    
    def save_instagram_data(self, user_id, username, password, media_path=None):
        """Save Instagram credentials and optionally media to Google Drive.
        
        Args:
            user_id: Telegram user ID
            username: Instagram username
            password: Instagram password
            media_path: Path to media file (optional)
            
        Returns:
            dict: Dictionary with saved data info
        """
        # Create a user folder
        user_folder_name = f"user_{user_id}"
        user_folder_id = self._get_or_create_folder(user_folder_name, self.root_folder_id)
        
        # Save credentials as JSON
        credentials = {
            'user_id': user_id,
            'username': username,
            'password': password
        }
        
        creds_path = f"temp_creds_{user_id}.json"
        with open(creds_path, 'w') as f:
            json.dump(credentials, f)
        
        # Upload credentials file
        creds_file_id = self.upload_file(creds_path, user_folder_name)
        
        # Clean up the temporary credentials file
        if os.path.exists(creds_path):
            os.remove(creds_path)
        
        result = {
            'user_folder_id': user_folder_id,
            'credentials_file_id': creds_file_id
        }
        
        # Upload media if provided
        if media_path and os.path.exists(media_path):
            media_file_id = self.upload_file(media_path, user_folder_name)
            result['media_file_id'] = media_file_id
        
        return result
    
    def load_all_credentials(self):
        """Load all Instagram credentials stored in Google Drive.
        
        Returns:
            list: List of credential dictionaries
        """
        all_credentials = []
        
        # Get all user folders
        query = f"'{self.root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        user_folders = results.get('files', [])
        
        for folder in user_folders:
            if folder['name'].startswith('user_'):
                # Look for credentials file in this folder
                creds_query = f"'{folder['id']}' in parents and name contains 'creds' and trashed=false"
                creds_results = self.service.files().list(
                    q=creds_query,
                    spaces='drive',
                    fields='files(id, name)'
                ).execute()
                
                creds_files = creds_results.get('files', [])
                
                if creds_files:
                    # Download and parse the first credentials file
                    creds_file_id = creds_files[0]['id']
                    temp_path = f"temp_download_{folder['name']}.json"
                    
                    if self.download_file(creds_file_id, temp_path):
                        try:
                            with open(temp_path, 'r') as f:
                                credentials = json.load(f)
                                all_credentials.append(credentials)
                            
                            # Clean up
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                                
                        except Exception as e:
                            logger.error(f"Error parsing credentials file: {str(e)}")
        
        return all_credentials
    
    def load_user_credentials(self, user_id):
        """Load a specific user's Instagram credentials from Google Drive.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            dict or None: Credentials dictionary if found, None otherwise
        """
        # Check if user folder exists
        user_folder_name = f"user_{user_id}"
        query = f"name='{user_folder_name}' and '{self.root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        folders = results.get('files', [])
        
        if not folders:
            return None
        
        folder_id = folders[0]['id']
        
        # Look for credentials file in this folder
        creds_query = f"'{folder_id}' in parents and name contains 'creds' and trashed=false"
        creds_results = self.service.files().list(
            q=creds_query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        creds_files = creds_results.get('files', [])
        
        if not creds_files:
            return None
        
        # Download and parse the credentials file
        creds_file_id = creds_files[0]['id']
        temp_path = f"temp_download_{user_id}.json"
        
        if self.download_file(creds_file_id, temp_path):
            try:
                with open(temp_path, 'r') as f:
                    credentials = json.load(f)
                
                # Clean up
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return credentials
                
            except Exception as e:
                logger.error(f"Error parsing credentials file: {str(e)}")
        
        return None
