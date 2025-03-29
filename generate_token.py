import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define the scopes for Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate():
    """Authenticate with Google Drive API and save token."""
    creds = None
    credentials_file = 'credentials.json'
    token_file = 'token.json'
    
    logger.info(f"Initializing Google Drive with credentials file: {credentials_file}")
    
    # Check if token.json exists
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_info(
                eval(open(token_file, 'r').read()), SCOPES)
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
    
    # If there are no valid credentials, authenticate
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(str(creds.to_json()))
        logger.info(f"Saved new credentials to {token_file}")
    
    # Build the service
    service = build('drive', 'v3', credentials=creds)
    
    # Test the connection by getting the about info
    about = service.about().get(fields="user").execute()
    logger.info(f"Successfully authenticated as: {about['user']['emailAddress']}")
    
    return service

if __name__ == '__main__':
    print("===== GENERATING GOOGLE DRIVE TOKEN =====")
    service = authenticate()
    print("===== TOKEN GENERATED SUCCESSFULLY =====")
    print(f"Token saved to token.json")
    print("Now you can run encode_credentials.py to get the encoded values for Render")
