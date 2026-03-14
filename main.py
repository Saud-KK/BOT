import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os
import aiohttp
import re # For finding links

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

# The Toggle Switch
bridge_enabled = True

@bot.event
async def on_ready():
    print(f'Bridge System Ready: {bot.user.name}')

# --- COMMANDS ---

@bot.command()
async def toggle(ctx):
    """Command to turn the bridge ON or OFF"""
    global bridge_enabled
    if ctx.author.id != MY_USER_ID:
        return # Only you can control the bridge
    
    bridge_enabled = not bridge_enabled
    status = "ENABLED" if bridge_enabled else "DISABLED"
    await ctx.send(f"⚠️ **Bridge is now {status}**")

# --- HELPER: LINK DETECTION ---
def create_link_embed(content):
    """Detects links and wraps them in a Rich Embed."""
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, content)
    
    if urls:
        embed = discord.Embed(
            title="🔗 Shared Link",
            description=content,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Rich Link Preview")
        return embed
    return None

# --- CORE LOGIC ---

@bot.event
async def on_message(message):
    global bridge_enabled
    
    # 1. Protection & Loops
    if message.author.bot or message.webhook_id:
        return

    # 2. Allow the !toggle command to work even if bridge is off
    await bot.process_commands(message)

    # 3. Stop here if bridge is disabled
    if not bridge_enabled:
        return

    # --- DIRECTION: Source -> Target (Bot sends Rich Embeds) ---
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            files = [await a.to_file() for a in message.attachments]
            embed = create_link_embed(message.content)
            
            if embed:
                await target_channel.send(embed=embed, files=files)
            else:
                await target_channel.send(content=message.content, files=files)

    # --- DIRECTION: Target -> Source (Webhook Mirroring) ---
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
