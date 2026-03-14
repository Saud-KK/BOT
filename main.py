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
        intents.reactions = True # Required to detect reactions
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Syncing slash commands...")

bot = MyBot()

# --- CONFIG ---
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
MY_USER_ID = int(os.environ.get("MY_USER_ID", 0))

# MAPPING: {mirrored_message_id: original_message_id}
message_map = {}
bridge_enabled = True

@bot.event
async def on_ready():
    print(f'Sync Bridge Active: {bot.user.name}')

# --- REACTION MIRRORING LOGIC ---

@bot.event
async def on_raw_reaction_add(payload):
    """Detects when you react in Source and applies it to Target."""
    # 1. Only trigger if YOU are the one reacting
    if payload.user_id != MY_USER_ID:
        return

    # 2. Check if the reaction happened in your Source channel
    if payload.channel_id == SOURCE_CHANNEL_ID:
        # 3. Check if this message is one the bot mirrored
        if payload.message_id in message_map:
            target_msg_id = message_map[payload.message_id]
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            
            if target_channel:
                try:
                    # Fetch the original message and add the emoji
                    original_msg = await target_channel.fetch_message(target_msg_id)
                    await original_msg.add_reaction(payload.emoji)
                except Exception as e:
                    print(f"Reaction Sync Error: {e}")

# --- SLASH COMMANDS ---

@bot.command()
async def sync(ctx):
    if ctx.author.id == MY_USER_ID:
        await bot.tree.sync()
        await ctx.send("✅ Slash commands synced!")

@bot.tree.command(name="toggle", description="Turn the bridge ON or OFF (Private)")
async def toggle(interaction: discord.Interaction):
    global bridge_enabled
    if interaction.user.id != MY_USER_ID:
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return
    bridge_enabled = not bridge_enabled
    status = "ENABLED" if bridge_enabled else "DISABLED"
    await interaction.response.send_message(f"⚠️ Bridge is {status}", ephemeral=True)

# --- SCRAPER & CORE LOGIC ---

async def get_site_metadata(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    soup = BeautifulSoup(await resp.text(), 'html.parser')
                    t = soup.find("meta", property="og:title")
                    d = soup.find("meta", property="og:description")
                    i = soup.find("meta", property="og:image")
                    return {
                        "title": t["content"] if t else soup.title.string if soup.title else "Link",
                        "description": d["content"] if d else "Click to view.",
                        "image": i["content"] if i else None
                    }
    except: return None

@bot.event
async def on_message(message):
    global bridge_enabled
    if message.author.bot or message.webhook_id: return
    await bot.process_commands(message)
    if not bridge_enabled: return

    # Source -> Target
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            # We don't map these because you don't need to react to yourself
            await target_channel.send(content=message.content)

    # Target -> Source (The Mapping Happens Here)
    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            
            # Sending with wait=True returns the message object so we get the ID
            mirrored_msg = await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                wait=True 
            )
            
            # Save the link: {SourceID: TargetID}
            message_map[mirrored_msg.id] = message.id
            
            # Keep map small to prevent memory leaks (keep last 100 messages)
            if len(message_map) > 100:
                first_key = next(iter(message_map))
                del message_map[first_key]

# --- START ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
