import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, redirect, url_for
from threading import Thread
import os
import aiohttp
import re
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime

# --- SHARED DATA ---
bridge_data = {
    "enabled": True,
    "latest_msg": {
        "author": "No messages yet",
        "content": "Waiting for bridge activity...",
        "avatar": "https://cdn.discordapp.com/embed/avatars/0.png",
        "reactions": [],
        "time": ""
    }
}

# --- FLASK WEB SERVER ---
# Flask automatically looks for the 'templates' and 'static' folders
app = Flask(__name__)

@app.route('/')
def home():
    # Renders the index.html from the templates folder
    return render_template('index.html', data=bridge_data)

@app.route('/web-toggle')
def web_toggle():
    bridge_data["enabled"] = not bridge_data["enabled"]
    return redirect(url_for('home'))

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT LOGIC ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix="!", intents=intents)

bot = MyBot()

# Fetch environment variables
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
MY_USER_ID = int(os.environ.get("MY_USER_ID", 0))

message_map = {}

@bot.event
async def on_ready():
    print(f'Sync Bridge Active: {bot.user.name}')

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id != MY_USER_ID: return
    
    # Update reactions on Dashboard
    if payload.message_id in message_map or payload.message_id == bridge_data["latest_msg"].get("id"):
        emoji_str = str(payload.emoji)
        if emoji_str not in bridge_data["latest_msg"]["reactions"]:
            bridge_data["latest_msg"]["reactions"].append(emoji_str)

    # Sync reaction to target server
    if payload.channel_id == SOURCE_CHANNEL_ID:
        if payload.message_id in message_map:
            target_msg_id = message_map[payload.message_id]
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                try:
                    original_msg = await target_channel.fetch_message(target_msg_id)
                    await original_msg.add_reaction(payload.emoji)
                except: pass

@bot.tree.command(name="toggle", description="Turn bridge ON/OFF (Private)")
async def toggle(interaction: discord.Interaction):
    if interaction.user.id != MY_USER_ID:
        await interaction.response.send_message("Unauthorized", ephemeral=True)
        return
    bridge_data["enabled"] = not bridge_data["enabled"]
    status = "ENABLED" if bridge_data["enabled"] else "DISABLED"
    await interaction.response.send_message(f"Bridge is now {status}", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.bot or message.webhook_id: return
    if not bridge_data["enabled"]: return

    # Update Dashboard Data
    bridge_data["latest_msg"] = {
        "id": message.id,
        "author": message.author.display_name,
        "content": message.content if message.content else "[Attachment/Media]",
        "avatar": message.author.display_avatar.url,
        "reactions": [],
        "time": datetime.now().strftime("%H:%M:%S")
    }

    # Source -> Target
    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            await target_channel.send(content=message.content)

    # Target -> Source
    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            mirrored_msg = await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                wait=True 
            )
            message_map[mirrored_msg.id] = message.id
            if len(message_map) > 100: message_map.pop(next(iter(message_map)))

if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token: bot.run(token)
