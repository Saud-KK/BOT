import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os
import aiohttp
import re
import requests
from bs4 import BeautifulSoup

# --- FLASK WEB SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bridge Status: Online"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT CONFIG ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SETTINGS & CONFIG ---
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
MY_USER_ID = int(os.environ.get("MY_USER_ID", 0))

bridge_enabled = True

@bot.event
async def on_ready():
    print(f'Smart Bridge Active: {bot.user.name}')

# --- COMMANDS ---

@bot.command()
async def toggle(ctx):
    global bridge_enabled
    if ctx.author.id != MY_USER_ID:
        return
    
    bridge_enabled = not bridge_enabled
    status = "ENABLED" if bridge_enabled else "DISABLED"
    await ctx.send(f"⚠️ **Bridge is now {status}**")

# --- SMART SCRAPER: LINK PREVIEWS ---
def get_site_metadata(url):
    """Scrapes Title, Description, and Image from a URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Try to find OpenGraph tags (used by most modern sites)
        title = soup.find("meta", property="og:title")
        desc = soup.find("meta", property="og:description")
        image = soup.find("meta", property="og:image")

        return {
            "title": title["content"] if title else soup.title.string if soup.title else "Link Preview",
            "description": desc["content"] if desc else "Click the link to view more.",
            "image": image["content"] if image else None
        }
    except Exception:
        return None

def create_smart_embed(content):
    """Detects links and builds a Smart Rich Embed."""
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, content)
    
    if urls:
        url = urls[0] # Take the first link
        data = get_site_metadata(url)
        
        if data:
            embed = discord.Embed(
                title=data["title"],
                url=url,
                description=data["description"],
                color=discord.Color.gold()
            )
            if data["image"]:
                embed.set_thumbnail(url=data["image"])
            embed.set_footer(text=f"Shared via Mirror Bridge • {url}")
            return embed
    return None

# --- CORE LOGIC ---

@bot.event
async def on_message(message):
    global bridge_enabled
    
    if message.author.bot or message.webhook_id:
        return

    await bot.process_commands(message)

    if not bridge_enabled:
        return

    # --- Source -> Target (Smart Embeds) ---
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            files = [await a.to_file() for a in message.attachments]
            embed = create_smart_embed(message.content)
            
            if embed:
                await target_channel.send(embed=embed, files=files)
            else:
                await target_channel.send(content=message.content, files=files)

    # --- Target -> Source (Webhook Mirroring) ---
    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            files = [await a.to_file() for a in message.attachments]
            
            await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=files
            )

# --- START ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
