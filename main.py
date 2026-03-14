import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os
import aiohttp

# --- FLASK WEB SERVER (Render/Uptime) ---
app = Flask('')

@app.route('/')
def home():
    return "Bridge is Online"

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

# --- CONFIG ---
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

@bot.event
async def on_ready():
    print(f'Mirror Bridge Active: {bot.user.name}')

@bot.event
async def on_message(message):
    # 1. Prevent infinite loops (Ignore bots and webhooks)
    if message.author.bot or message.webhook_id:
        return

    # --- DIRECTION 1: Source -> Target (Bot sends normally) ---
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            files = [await a.to_file() for a in message.attachments]
            # Bot sends as itself
            await target_channel.send(content=message.content, files=files)

    # --- DIRECTION 2: Target -> Source (Webhook impersonates users) ---
    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            
            files = [await a.to_file() for a in message.attachments]
            
            # Webhook mirrors the Target user's name/avatar into Source
            await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=files
            )

    await bot.process_commands(message)

# --- START ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Missing DISCORD_TOKEN.")
