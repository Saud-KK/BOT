import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, redirect, url_for, request
from threading import Thread
import os
import aiohttp
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
app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html', data=bridge_data)

@app.route('/web-toggle')
def web_toggle():
    bridge_data["enabled"] = not bridge_data["enabled"]
    return redirect(url_for('home'))

@app.route('/broadcast', methods=['POST'])
def broadcast():
    # Collect all form data
    msg_type = request.form.get('type') # 'plain' or 'embed'
    content = request.form.get('message')
    title = request.form.get('title')
    color_hex = request.form.get('color', '#00ffff').lstrip('#')
    thumb = request.form.get('thumbnail')

    if content or title:
        # Convert hex string to integer for Discord
        color_int = int(color_hex, 16)
        
        asyncio.run_coroutine_threadsafe(
            send_web_msg(msg_type, content, title, color_int, thumb), bot.loop
        )
    return redirect(url_for('home'))

@app.route('/audit')
def audit_log():
    # Filter from URL: /audit?type=member_kick
    filter_type = request.args.get('type', None)
    
    # Run the async fetcher in the bot's loop
    future = asyncio.run_coroutine_threadsafe(
        fetch_audit_logs(filter_type), bot.loop
    )
    logs = future.result() # Wait for the bot to return the logs
    return render_template('audit.html', logs=logs, current_filter=filter_type)

async def send_web_msg(msg_type, content, title, color, thumb):
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not target_channel: return

    if msg_type == 'embed':
        embed = discord.Embed(
            title=title if title else None,
            description=content if content else None,
            color=color,
            timestamp=datetime.now()
        )
        if thumb and thumb.startswith("http"):
            embed.set_thumbnail(url=thumb)
        embed.set_footer(text="AI CHATBOT")
        await target_channel.send(embed=embed)
    else:
        # Fallback to plain text if no embed selected
        await target_channel.send(content=content)

async def fetch_audit_logs(filter_type=None):
    guild = bot.get_guild(int(os.environ.get("GUILD_ID", 0)))
    if not guild: return []
    
    logs = []
    # Fetch last 20 entries
    async for entry in guild.audit_logs(limit=20):
        # Apply filter if selected
        if filter_type and entry.action.name != filter_type:
            continue
            
        logs.append({
            "user": entry.user.display_name,
            "action": entry.action.name.replace('_', ' ').title(),
            "target": str(entry.target),
            "time": entry.created_at.strftime("%b %d, %H:%M")
        })
    return logs

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
        intents.guilds = True # Needed for Audit Logs
        super().__init__(command_prefix="!", intents=intents)

bot = MyBot()

SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
MY_USER_ID = int(os.environ.get("MY_USER_ID", 0))

message_map = {}

@bot.event
async def on_ready():
    print(f'Sync Bridge Active: {bot.user.name}')

@bot.event
async def on_message(message):
    if message.author.bot or message.webhook_id: return
    if not bridge_data["enabled"]: return

    bridge_data["latest_msg"] = {
        "id": message.id,
        "author": message.author.display_name,
        "content": message.content if message.content else "[Media]",
        "avatar": message.author.display_avatar.url,
        "reactions": [],
        "time": datetime.now().strftime("%H:%M:%S")
    }

    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel: await target_channel.send(content=message.content)

    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            mirrored_msg = await webhook.send(
                content=message.content, username=message.author.display_name,
                avatar_url=message.author.display_avatar.url, wait=True 
            )
            message_map[mirrored_msg.id] = message.id

if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token: bot.run(token)
