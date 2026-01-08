import discord
from discord.ext import commands
import aiohttp
import os
import logging
from datetime import datetime, timezone, timedelta, time, date
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import asyncio
import random
from io import BytesIO
from PIL import Image
import urllib.parse
import praw

# --- INITIAL SETUP ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

REQUIRED_KEYS = [
    "DISCORD_BOT_TOKEN",
    "OPENWEATHER_API_KEY",
    "VISUALCROSSING_API_KEY",
    "UNSPLASH_API_KEY",
]
for key in REQUIRED_KEYS:
    if not os.getenv(key):
        raise RuntimeError(f"Missing required environment variable: {key}")

CONFIG = {
    "DISCORD_TOKEN": os.getenv("DISCORD_BOT_TOKEN"),
    "OPENWEATHER_KEY": os.getenv("OPENWEATHER_API_KEY"),
    "VISUAL_KEY": os.getenv("VISUALCROSSING_API_KEY"),
    "UNSPLASH_KEY": os.getenv("UNSPLASH_API_KEY"),
    "AUTO_CHANNEL_ID": os.getenv("AUTO_CHANNEL_ID"),
    "LOCATION": {"lat": 22.5726, "lon": 88.3639, "city": "Kolkata"},
    "TIMEZONE": ZoneInfo("Asia/Kolkata"),
    "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
    "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
    "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", "DailyBriefingBot/1.0"),
}

intents = discord.Intents.default()
intents.message_content = True

class DailyBriefingBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.add_cog(Briefing(self))

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Kolkata skies & desi vibes 🌤️😂"))
        logging.info(f"Logged in as {self.user}")

class Briefing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = bot.session
        self._historical_cache = None
        self._historical_date = None
        self.scheduled_hours = [7, 13, 18, 22]
        self.timezone = CONFIG["TIMEZONE"]
        self.scheduler_started = False
        self.status_started = False
        self.bg_task = None
        self.status_task = None
        self.used_meme_ids = set()
        self.meme_reset_date = None
        self.fallback_statuses = [
            "Kolkata skies & desi vibes 🌤️😂",
            "Craving puchka & rosogolla 🍲🍬",
            "Lost in Kolkata traffic 🚕😂",
            "Dreaming of Durga Puja 🛕",
            "Adda session loading ☕",
            "Howrah Bridge admirer 🌉",
            "Eden Gardens cheering 🏏",
            "Vibing with tram bells 🚋",
            "Waiting for monsoon magic ☔",
            "Desi meme hunter on duty 😂",
        ]
        self.subreddits = [
            "indiameme",
            "IndianDankMemes",
            "dankrishu",
            "desimemes",
            "indianmemer",
            "IndiaMemes"
        ]
        self.reddit = None
        if CONFIG.get("REDDIT_CLIENT_ID") and CONFIG.get("REDDIT_CLIENT_SECRET"):
            try:
                self.reddit = praw.Reddit(
                    client_id=CONFIG["REDDIT_CLIENT_ID"],
                    client_secret=CONFIG["REDDIT_CLIENT_SECRET"],
                    user_agent=CONFIG["REDDIT_USER_AGENT"],
                )
                logging.info("PRAW initialized successfully")
            except Exception as e:
                logging.error(f"PRAW initialization failed: {e}")
        logging.info("Briefing cog loaded successfully")

    async def fetch_json(self, url, headers=None):
        async with self.session.get(url, headers=headers or {}, timeout=15) as resp:
            if resp.status != 200:
                logging.warning(f"API error {resp.status}: {url}")
                return None
            try:
                return await resp.json()
            except Exception as e:
                logging.error(f"JSON decode error for {url}: {e}")
                return None

    async def download_and_process_media(self, url: str):
        try:
            headers = {"User-Agent": "DailyBriefingBot/1.0"}
            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logging.warning(f"Failed to download {url} - status {resp.status}")
                    return None
                data = await resp.read()
                if len(data) == 0:
                    logging.warning(f"Empty data from {url}")
                    return None
            input_buffer = BytesIO(data)
            try:
                img = Image.open(input_buffer)
            except Exception as e:
                logging.error(f"Pillow cannot open image from {url}: {e}")
                return None
            is_animated = getattr(img, "is_animated", False)
            n_frames = getattr(img, "n_frames", 1) if is_animated else 1
            original_format = img.format
            input_buffer.seek(0)
            TARGET_WIDTH = 1200
            TARGET_HEIGHT = 675
            frames = []
            durations = []
            if is_animated and original_format == "GIF" and n_frames > 1:
                for i in range(n_frames):
                    try:
                        img.seek(i)
                        frame = img.convert("RGB")
                        duration = img.info.get("duration", 100)
                        durations.append(duration)
                        frame.thumbnail((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
                        new_frame = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
                        paste_pos = ((TARGET_WIDTH - frame.width) // 2, (TARGET_HEIGHT - frame.height) // 2)
                        new_frame.paste(frame, paste_pos)
                        frames.append(new_frame)
                    except EOFError:
                        break
            else:
                img = img.convert("RGB")
                img.thumbnail((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
                new_img = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
                paste_pos = ((TARGET_WIDTH - img.width) // 2, (TARGET_HEIGHT - img.height) // 2)
                new_img.paste(img, paste_pos)
                frames.append(new_img)
                durations = [100]
            output_buffer = BytesIO()
            if len(frames) > 1:
                frames[0].save(
                    output_buffer,
                    format="GIF",
                    append_images=frames[1:],
                    save_all=True,
                    duration=durations,
                    loop=0,
                )
                filename = "meme.gif"
            else:
                frames[0].save(output_buffer, format="PNG")
                filename = "meme.png"
            output_buffer.seek(0)
            if output_buffer.getbuffer().nbytes == 0:
                logging.error("Output buffer empty after saving")
                return None
            return discord.File(output_buffer, filename=filename)
        except Exception as e:
            logging.error(f"Error processing media {url}: {e}")
            return None

    async def get_reddit_meme(self):
        today = date.today()
        if self.meme_reset_date != today:
            self.used_meme_ids.clear()
            self.meme_reset_date = today
        if not self.reddit:
            logging.warning("Reddit credentials missing — no memes today")
            return None, None
        random.shuffle(self.subreddits)
        for sub in self.subreddits:
            try:
                subreddit = self.reddit.subreddit(sub)
                candidates = []
                for post in subreddit.hot(limit=100):
                    if post.over_18 or post.stickied or getattr(post, "is_video", False):
                        continue
                    if post.name in self.used_meme_ids:
                        continue
                    media_url = post.url
                    if media_url.lower().endswith('.gifv'):
                        media_url = media_url[:-4] + '.gif'
                    title = post.title.strip() or "Desi Meme 😂"
                    if media_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        candidates.append((media_url, post.score, title, post.name))
                if candidates:
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    top_10 = candidates[:10]
                    if top_10:
                        chosen_url, _, chosen_title, chosen_id = random.choice(top_10)
                        file = await self.download_and_process_media(chosen_url)
                        if file:
                            self.used_meme_ids.add(chosen_id)
                            return file, chosen_title
            except Exception as e:
                logging.warning(f"Error fetching from r/{sub}: {e}")
                continue
        logging.info("No suitable meme found today")
        return None, None

    async def get_current_weather(self):
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={CONFIG['LOCATION']['lat']}&lon={CONFIG['LOCATION']['lon']}&appid={CONFIG['OPENWEATHER_KEY']}&units=metric"
        return await self.fetch_json(url)

    async def get_forecast(self):
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={CONFIG['LOCATION']['lat']}&lon={CONFIG['LOCATION']['lon']}&appid={CONFIG['OPENWEATHER_KEY']}&units=metric"
        return await self.fetch_json(url)

    async def get_daily_min_max(self):
        data = await self.get_forecast()
        if not data or 'list' not in data:
            return None, None
        today = datetime.now(self.timezone).date()
        temps = []
        for item in data['list']:
            dt = datetime.fromtimestamp(item['dt'], timezone.utc).astimezone(self.timezone)
            if dt.date() == today:
                temps.append(item['main']['temp'])
        if temps:
            return round(min(temps)), round(max(temps))
        return None, None

    async def get_air_quality(self):
        url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={CONFIG['LOCATION']['lat']}&lon={CONFIG['LOCATION']['lon']}&appid={CONFIG['OPENWEATHER_KEY']}"
        data = await self.fetch_json(url)
        if data and 'list' in data and data['list']:
            aqi = data['list'][0]['main']['aqi']
            aqi_desc = {1: "Good 🟢", 2: "Fair 🟡", 3: "Moderate 🟠", 4: "Poor 🔴", 5: "Very Poor ⚫"}.get(aqi, "Unknown")
            return aqi_desc
        return "N/A"

    async def get_historical_weather(self):
        today = datetime.now(self.timezone).date()
        if self._historical_date == today and self._historical_cache:
            return self._historical_cache
        last_year_date = (datetime.now(self.timezone) - timedelta(days=365)).strftime("%Y-%m-%d")
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{CONFIG['LOCATION']['city']}/{last_year_date}/{last_year_date}?unitGroup=metric&key={CONFIG['VISUAL_KEY']}&contentType=json"
        data = await self.fetch_json(url)
        result = data["days"][0] if data and data.get("days") else None
        self._historical_cache = result
        self._historical_date = today
        return result

    def get_season(self):
        month = datetime.now(CONFIG["TIMEZONE"]).month
        if month in (3, 4, 5): return "summer"
        if month in (6, 7, 8, 9): return "monsoon"
        if month in (10, 11): return "autumn"
        return "winter"

    def map_weather_to_image_query(self, weather_id: int, is_night: bool):
        landmarks = random.choice([
            "Howrah Bridge Kolkata",
            "Victoria Memorial Kolkata",
            "Ganges river Kolkata",
            "Kolkata skyline",
            "Prinsep Ghat Kolkata",
            "yellow taxi Kolkata streets",
            "Dakshineswar Temple Kolkata",
            "Eden Gardens Kolkata"
        ])
        time_part = "night illuminated" if is_night else "daytime"
        weather_term = ""
        if 200 <= weather_id < 300:
            weather_term = "thunderstorm dramatic lightning"
        elif 300 <= weather_id < 600:
            weather_term = "heavy rain monsoon wet streets"
        elif 600 <= weather_id < 700:
            weather_term = "snow"
        elif 700 <= weather_id < 800:
            weather_term = "foggy misty morning"
        elif weather_id == 800:
            weather_term = "clear blue sky sunny beautiful"
        elif 801 <= weather_id <= 804:
            weather_term = "partly cloudy sky"
        return f"Kolkata {landmarks} {weather_term} {time_part} cityscape landscape photography India horizontal"

    async def get_unsplash_image(self, query):
        encoded_query = urllib.parse.quote(query)
        page = random.randint(1, 10)
        headers = {"Authorization": f"Client-ID {CONFIG['UNSPLASH_KEY']}"}
        url = f"https://api.unsplash.com/search/photos?query={encoded_query}&per_page=30&orientation=landscape&page={page}"
        data = await self.fetch_json(url, headers=headers)
        if not data or "results" not in data or not data["results"]:
            page = 1
            url = f"https://api.unsplash.com/search/photos?query={encoded_query}&per_page=30&orientation=landscape&page=1"
            data = await self.fetch_json(url, headers=headers)
        ultimate_fallback = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/Kolkata_skyline_from_Hooghly_bridge.jpg/1280px-Kolkata_skyline_from_Hooghly_bridge.jpg"
        if data and "results" in data and data["results"]:
            candidates = [photo["urls"]["regular"] for photo in data["results"]]
            return random.choice(candidates)
        logging.warning(f"Unsplash failed - using fallback")
        return ultimate_fallback

    async def get_image(self, query):
        return await self.get_unsplash_image(query)

    def get_weather_emoji(self, weather_main):
        return {
            "Clear": "☀️", "Clouds": "☁️", "Drizzle": "🌧️", "Rain": "🌧️",
            "Thunderstorm": "⛈️", "Snow": "❄️", "Mist": "🌫️", "Fog": "🌫️"
        }.get(weather_main, "🌤️")

    def get_wind_direction(self, deg):
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = int((deg + 11.25) / 22.5) % 16
        return directions[idx]

    async def cycle_status(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            curr = await self.get_current_weather()
            if curr and "main" in curr and "weather" in curr:
                temp = round(curr["main"]["temp"])
                feels = round(curr["main"]["feels_like"])
                weather = curr["weather"][0]
                emoji = self.get_weather_emoji(weather["main"])
                desc = weather["description"]
                # Removed the em dash after the emoji
                status_name = f"Kolkata: {temp}°C (feels {feels}°C) {emoji} {desc.capitalize()}"
            else:
                status_name = random.choice(self.fallback_statuses)
            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_name))
            await asyncio.sleep(1800)

    async def build_weather_embed(self):
        curr = await self.get_current_weather()
        past = await self.get_historical_weather()
        if not curr:
            return discord.Embed(title="Weather in Kolkata", description="Unable to fetch data.", color=0xE74C3C)
        weather = curr["weather"][0]
        main = weather["main"]
        temp = round(curr["main"]["temp"])
        feels = round(curr["main"]["feels_like"])
        humid = curr["main"]["humidity"]
        wind_speed = round(curr["wind"]["speed"] * 3.6, 1)
        wind_deg = curr["wind"].get("deg", 0)
        wind_dir = self.get_wind_direction(wind_deg)
        vis = round(curr.get("visibility", 0) / 1000, 1)
        sunrise_dt = datetime.fromtimestamp(curr["sys"]["sunrise"], timezone.utc).astimezone(self.timezone)
        sunset_dt = datetime.fromtimestamp(curr["sys"]["sunset"], timezone.utc).astimezone(self.timezone)
        sunrise = sunrise_dt.strftime("%I:%M %p")
        sunset = sunset_dt.strftime("%I:%M %p")
        is_night = weather["icon"].endswith("n")
        image_query = self.map_weather_to_image_query(weather["id"], is_night)
        color = 0x3498DB if temp < 20 else 0xF39C12 if temp < 30 else 0xE74C3C
        emoji = self.get_weather_emoji(main)
        temp_min, temp_max = await self.get_daily_min_max()
        if temp_min is None:
            temp_min = round(curr["main"]["temp_min"])
            temp_max = round(curr["main"]["temp_max"])
        aqi = await self.get_air_quality()
        image_url = await self.get_image(image_query)
        embed = discord.Embed(
            title=f"{emoji} Weather in Kolkata • {weather['description'].capitalize()}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🌡️ Temperature", value=f"{temp}°C", inline=True)
        embed.add_field(name="😌 Feels Like", value=f"{feels}°C", inline=True)
        embed.add_field(name="📉 Low / High", value=f"{temp_min}°C / {temp_max}°C", inline=True)
        embed.add_field(name="💧 Humidity", value=f"{humid}%", inline=True)
        embed.add_field(name="🌬️ Wind", value=f"{wind_speed} km/h {wind_dir}", inline=True)
        embed.add_field(name="👀 Visibility", value=f"{vis} km", inline=True)
        embed.add_field(name="🌫️ Air Quality", value=aqi, inline=True)
        embed.add_field(name="🌅 Sunrise / Sunset", value=f"{sunrise} / {sunset}", inline=False)
        if past:
            p_temp = round(past.get("temp", temp))
            diff = temp - p_temp
            trend = "warmer 📈" if diff > 0 else "cooler 📉" if diff < 0 else "same"
            embed.add_field(name="📅 Vs Last Year", value=f"{p_temp}°C ({abs(diff)}°C {trend})", inline=False)
        embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{weather['icon']}@4x.png")
        embed.set_image(url=image_url)
        embed.set_footer(text="OpenWeather • Visual Crossing • Reddit")
        return embed

    async def auto_post_loop(self):
        channel_id = CONFIG.get("AUTO_CHANNEL_ID")
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        await self.bot.wait_until_ready()
        logging.info("Auto-post scheduler started")
        while not self.bot.is_closed():
            now = datetime.now(self.timezone)
            today = now.date()
            next_time = None
            for h in self.scheduled_hours:
                candidate = datetime.combine(today, time(h, 0), tzinfo=self.timezone)
                if candidate > now:
                    next_time = candidate
                    break
            if not next_time:
                next_day = today + timedelta(days=1)
                next_time = datetime.combine(next_day, time(self.scheduled_hours[0], 0), tzinfo=self.timezone)
            sleep_secs = (next_time - now).total_seconds()
            await asyncio.sleep(sleep_secs)
            try:
                async with channel.typing():
                    meme_file, meme_title = await self.get_reddit_meme()
                    weather_embed = await self.build_weather_embed()
                    if meme_file:
                        meme_file.fp.seek(0)
                        # Plain image with bold title (no embed border)
                        meme_message = await channel.send(content=f"**{meme_title}**", file=meme_file)
                        await meme_message.add_reaction('👍')
                        await meme_message.add_reaction('👎')
                        await meme_message.add_reaction('😂')
                    else:
                        await channel.send("No fresh desi meme today 😢")
                    await channel.send(embed=weather_embed)
            except Exception as e:
                logging.error(f"Auto-post error: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.scheduler_started:
            self.scheduler_started = True
            self.bg_task = self.bot.loop.create_task(self.auto_post_loop())
        if not self.status_started:
            self.status_started = True
            self.status_task = self.bot.loop.create_task(self.cycle_status())

    def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()
        if self.status_task:
            self.status_task.cancel()

    @commands.command(name="briefing")
    async def briefing(self, ctx):
        async with ctx.typing():
            meme_file, meme_title = await self.get_reddit_meme()
            weather_embed = await self.build_weather_embed()
            if meme_file:
                meme_file.fp.seek(0)
                await ctx.send(content=f"**{meme_title}**", file=meme_file)
            else:
                await ctx.send("No fresh meme right now 😢")
            await ctx.send(embed=weather_embed)

    @commands.command(name="test")
    async def test(self, ctx):
        await ctx.message.add_reaction("🧪")
        await self.briefing(ctx)

bot = DailyBriefingBot()
bot.run(CONFIG["DISCORD_TOKEN"])