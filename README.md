# NSG Weather Bot

A simple Discord bot for the NSG server that delivers daily Kolkata weather updates with beautiful cityscape backgrounds and a fresh desi meme.

Perfect for starting your day with local weather info and a quick laugh! 🌤️😂

## Features

- Current Kolkata weather: temperature, feels-like, humidity, wind, visibility, AQI, sunrise/sunset, daily low/high
- Compared to last year on the same day
- Stunning Kolkata-themed background images (weather-matched)
- One fresh desi meme daily (no repeats, no videos/NSFW)
- Auto-posts at 7 AM, 1 PM, 6 PM, 10 PM IST
- Dynamic bot status with live Kolkata weather
- Manual commands: `!briefing` or `!test`

## Setup (for hosting your own)

1. Create a `.env` file:

```env
DISCORD_BOT_TOKEN=your_bot_token

OPENWEATHER_API_KEY=your_key
VISUALCROSSING_API_KEY=your_key
UNSPLASH_API_KEY=your_key

REDDIT_CLIENT_ID=your_reddit_id
REDDIT_CLIENT_SECRET=your_reddit_secret
REDDIT_USER_AGENT=NSGWeatherBot/1.0 (by u/your_username)

AUTO_CHANNEL_ID=your_channel_id  # Channel for auto-posts

Install dependencies:

pip install discord.py praw aiohttp python-dotenv Pillow

Run:

python main.py

Commands

!briefing → Send weather + meme now
!test → Same as briefing (with 🧪 reaction)

Made for NSG server with ❤️
