import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
import os
import aiohttp
import re
from bs4 import BeautifulSoup
import asyncio

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
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # This prepares the slash commands
        print("Syncing slash commands...")

bot = MyBot()

# --- SETTINGS ---
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
async def sync(ctx):
    """Run this ONCE to enable the /toggle command"""
    if ctx.author.id == MY_USER_ID:
        await bot.tree.sync()
        await ctx.send("✅ Slash commands synced!")

@bot.tree.command(name="toggle", description="Turn the bridge ON or OFF (Private)")
async def toggle(interaction: discord.Interaction):
    global bridge_enabled
    if interaction.user.id != MY_USER_ID:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    
    bridge_enabled = not bridge_enabled
    status = "ENABLED" if bridge_enabled else "DISABLED"
    # 'ephemeral=True' makes it invisible to others
    await interaction.response.send_message(f"⚠️ **Bridge is now {status}**", ephemeral=True)

# --- ASYNC SMART SCRAPER ---
async def get_site_metadata(url):
    """Asynchronous scraping to prevent freezing."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    title = soup.find("meta", property="og:title")
                    desc = soup.find("meta", property="og:description")
                    image = soup.find("meta", property="og:image")

                    return {
                        "title": title["content"] if title else soup.title.string if soup.title else "Link Preview",
                        "description": desc["content"] if desc else "Click to view more.",
                        "image": image["content"] if image else None
                    }
    except Exception as e:
        print(f"Scrape Error: {e}")
    return None

async def create_smart_embed(content):
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, content)
    
    if urls:
        url = urls[0]
        data = await get_site_metadata(url) # Using await here
        
        if data:
            embed = discord.Embed(
                title=data["title"],
                url=url,
                description=data["description"],
                color=discord.Color.gold()
            )
            if data["image"]:
                embed.set_thumbnail(url=data["image"])
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

    # Source -> Target
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            files = [await a.to_file() for a in message.attachments]
            embed = await create_smart_embed(message.content) # Await the embed
            
            if embed:
                await target_channel.send(embed=embed, files=files)
            else:
                await target_channel.send(content=message.content, files=files)

    # Target -> Source
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
