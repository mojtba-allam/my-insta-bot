import os
import base64

def setup_credentials():
    """Set up Google Drive credentials from base64-encoded environment variables for Render."""
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Check if we have base64-encoded credentials from environment variables
    credentials_base64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
    token_base64 = os.getenv('GOOGLE_TOKEN_BASE64')
    
    # If running on Render with base64 credentials
    if credentials_base64:
        print("Setting up Google credentials from environment variables")
        # Decode and save credentials.json
        credentials_data = base64.b64decode(credentials_base64)
        with open('credentials.json', 'wb') as f:
            f.write(credentials_data)
        print("Saved credentials.json")
    
    # If running on Render with base64 token
    if token_base64:
        print("Setting up Google token from environment variables")
        # Decode and save token.json
        token_data = base64.b64decode(token_base64)
        with open('token.json', 'wb') as f:
            f.write(token_data)
        print("Saved token.json")

if __name__ == "__main__":
    setup_credentials()
