# Instagram Bot

A Telegram bot that helps you download and repost Instagram content with custom captions. The bot maintains persistent login and automatically adds attribution to reposted content.

## Features

- Download and repost Instagram posts (photos, videos)
- Persistent login - log in once, repost multiple times
- Automatic attribution for original creators
- Local file storage for credentials and media
- Interactive caption editing through Telegram
- Secure credential handling

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Telegram bot token:
```
TELEGRAM_TOKEN=your_telegram_bot_token_here
```

4. Run the bot:
```bash
python main.py
```

## Usage

1. Start a chat with your bot on Telegram
2. Send the `/start` command
3. Send an Instagram post URL
4. Follow the bot's instructions to provide a new caption
5. The bot will download the content and prepare it for reposting

## GitLab Deployment

To deploy the bot to GitLab:

1. Create a new repository on GitLab

2. Initialize and push the repository:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://gitlab.com/your-username/instagram-bot.git
git push -u origin master
```

3. Set up GitLab CI/CD by creating a `.gitlab-ci.yml` file in your repository:
```bash
touch .gitlab-ci.yml
```

4. Deploy your bot to a server or use GitLab CI/CD for continuous deployment.

## Running on a Remote Server

### Method 1: Basic Server Setup

1. SSH into your server:
```bash
ssh username@your-server-ip
```

2. Clone your GitLab repository:
```bash
git clone https://gitlab.com/your-username/instagram-bot.git
cd instagram-bot
```

3. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. Create a `.env` file with your environment variables:
```bash
# Add your Telegram bot token and other configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here
USE_GOOGLE_DRIVE=true
GOOGLE_DRIVE_CREDENTIALS=credentials.json
DATA_DIR=data
```

5. Upload your Google Drive credentials file (credentials.json) to the server.

6. Start the bot (for testing):
```bash
python main.py
```

7. For production, use a process manager like `systemd` or `supervisor` to keep the bot running:

Using systemd:
```bash
sudo nano /etc/systemd/system/instagram-bot.service
```

Add the following content:
```
[Unit]
Description=Instagram Bot Service
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/instagram-bot
ExecStart=/path/to/instagram-bot/venv/bin/python /path/to/instagram-bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl enable instagram-bot.service
sudo systemctl start instagram-bot.service
```

### Method 2: Using Docker (Recommended)

1. Create a `Dockerfile` in your repository:
```bash
touch Dockerfile
```

2. Add the Docker configuration to the `Dockerfile`:
```
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

3. Create a `.env.docker` file (without sensitive information) for Docker:
```
TELEGRAM_TOKEN=your_telegram_bot_token_here
USE_GOOGLE_DRIVE=true
GOOGLE_DRIVE_CREDENTIALS=credentials.json
DATA_DIR=data
```

4. Build and push your Docker image:
```bash
docker build -t your-username/instagram-bot:latest .
docker push your-username/instagram-bot:latest
```

5. Deploy on your server using docker-compose:

Create a `docker-compose.yml` file:
```yaml
version: '3'

services:
  instagram-bot:
    image: your-username/instagram-bot:latest
    restart: always
    volumes:
      - ./data:/app/data
      - ./credentials.json:/app/credentials.json
      - ./.env:/app/.env
```

6. Start the container:
```bash
docker-compose up -d
```

### Method 3: Using GitLab CI/CD with Auto-Deployment

1. Set up GitLab Runner on your server
2. Create a `.gitlab-ci.yml` file with deployment steps
3. Configure GitLab CI/CD variables for sensitive information
4. Use GitLab's auto-deployment feature to automatically deploy changes

## Keeping Your Bot Running

- Use a process manager like `systemd` or Docker's restart policy
- Set up monitoring to alert you if the bot goes down
- Configure log rotation to prevent disk space issues
- Consider setting up backup mechanisms for your data directory

## Data Storage

The bot uses a simple local storage system:
- JSON files for storing user credentials and post data
- Local directory for storing media files
- Automatic file cleanup to manage storage
- All data is stored in the `data/` directory

## Note

To use the bot:
1. Make sure you have a valid Instagram account
2. Create a Telegram bot and get the token from @BotFather
3. Keep your credentials secure and never share them
4. The bot will automatically add attribution when reposting

## License

MIT
