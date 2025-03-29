import base64
import os

def encode_file(filename):
    """Encode a file to base64 and print the result."""
    if not os.path.exists(filename):
        print(f"Error: {filename} does not exist")
        return
    
    with open(filename, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
        print(f"\n=== {filename} Base64 Encoded ===")
        print(encoded)
        print(f"=== End of {filename} ===\n")
        return encoded

if __name__ == "__main__":
    print("Encoding Google Drive credentials and token for Render.com deployment")
    
    # Encode credentials.json
    if os.path.exists('credentials.json'):
        credentials = encode_file('credentials.json')
    else:
        print("Warning: credentials.json not found")
    
    # Encode token.json
    if os.path.exists('token.json'):
        token = encode_file('token.json')
    else:
        print("Warning: token.json not found. Make sure to run test_google_drive.py first!")
    
    print("Copy these encoded strings to Render.com environment variables:")
    print("GOOGLE_CREDENTIALS_BASE64: The encoded credentials.json value")
    print("GOOGLE_TOKEN_BASE64: The encoded token.json value")
