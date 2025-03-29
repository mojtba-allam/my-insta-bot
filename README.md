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
git remote add origin your_gitlab_repo_url
git push -u origin main
```

3. Set up environment variables in GitLab:
- Go to Settings > CI/CD > Variables
- Add `TELEGRAM_TOKEN` with your bot token

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
