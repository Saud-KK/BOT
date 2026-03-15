import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, redirect, url_for, request
from threading import Thread
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta

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
    future = asyncio.run_coroutine_threadsafe(get_human_members(), bot.loop)
    members = future.result()
    return render_template('index.html', data=bridge_data, members=members)

@app.route('/moderate', methods=['POST'])
def moderate():
    user_id = request.form.get('user_id')
    action = request.form.get('action') # 'kick', 'timeout', or 'ban'
    duration = int(request.form.get('duration', 10)) # Default to 10 if missing
    
    if user_id:
        asyncio.run_coroutine_threadsafe(
            perform_moderation(user_id, action, duration), bot.loop
        )
    return redirect(url_for('home'))

@app.route('/web-toggle')
def web_toggle():
    bridge_data["enabled"] = not bridge_data["enabled"]
    return redirect(url_for('home'))

@app.route('/broadcast', methods=['POST'])
def broadcast():
    msg_type = request.form.get('type')
    content = request.form.get('message')
    title = request.form.get('title')
    color_hex = request.form.get('color', '#00ffff').lstrip('#')
    thumb = request.form.get('thumbnail')
    if content or title:
        color_int = int(color_hex, 16)
        asyncio.run_coroutine_threadsafe(
            send_web_msg(msg_type, content, title, color_int, thumb), bot.loop
        )
    return redirect(url_for('home'))

@app.route('/audit')
def audit_log():
    filter_type = request.args.get('type', None)
    future = asyncio.run_coroutine_threadsafe(fetch_audit_logs(filter_type), bot.loop)
    logs = future.result()
    return render_template('audit.html', logs=logs, current_filter=filter_type)

# --- ASYNC BOT ACTIONS ---

async def get_human_members():
    guild = bot.get_guild(int(os.environ.get("GUILD_ID", 0)))
    if not guild: return []
    return sorted([{"id": m.id, "name": m.display_name} for m in guild.members if not m.bot], key=lambda x: x["name"])

async def perform_moderation(user_id, action, duration=10):
    guild = bot.get_guild(int(os.environ.get("GUILD_ID", 0)))
    if not guild: return
    
    try:
        if action == 'ban':
            # discord.Object allows us to ban users even if they aren't currently in the server cache
            user = discord.Object(id=int(user_id))
            await guild.ban(user, reason="Banned via Bridge/Dashboard")
        else:
            member = guild.get_member(int(user_id))
            if not member: return
            
            if action == 'kick':
                await member.kick(reason="Kicked via Bridge/Dashboard")
            elif action == 'timeout':
                await member.timeout(timedelta(minutes=duration), reason="Timed out via Bridge/Dashboard")
    except Exception as e:
        print(f"Moderation Error: {e}")

async def send_web_msg(msg_type, content, title, color, thumb):
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not target_channel: return
    if msg_type == 'embed':
        embed = discord.Embed(title=title, description=content, color=color, timestamp=datetime.now())
        if thumb and thumb.startswith("http"): embed.set_thumbnail(url=thumb)
        embed.set_footer(text="AI CHATBOT")
        await target_channel.send(embed=embed)
    else:
        await target_channel.send(content=content)

async def fetch_audit_logs(filter_type=None):
    guild = bot.get_guild(int(os.environ.get("GUILD_ID", 0)))
    if not guild: return []
    logs = []
    async for entry in guild.audit_logs(limit=20):
        if filter_type and entry.action.name != filter_type: continue
        logs.append({"user": entry.user.display_name, "action": entry.action.name.replace('_', ' ').title(), "target": str(entry.target), "time": entry.created_at.strftime("%b %d, %H:%M")})
    return logs

# --- DISCORD BOT CORE ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        intents.members = True 
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

# --- COMMANDS (Sync & Target Mod) ---

@bot.command()
async def sync(ctx):
    if ctx.author.id == MY_USER_ID:
        await bot.tree.sync()
        await ctx.send("✅ Slash commands synced!")

@bot.tree.command(name="tmod", description="Moderate a user in the target server")
@app_commands.describe(action="Select Action", user_id="User ID", duration="Timeout duration in minutes")
@app_commands.choices(action=[
    app_commands.Choice(name="Timeout", value="timeout"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Ban", value="ban")
])
async def tmod(interaction: discord.Interaction, action: app_commands.Choice[str], user_id: str, duration: int = 10):
    if interaction.user.id != MY_USER_ID:
        return await interaction.response.send_message("Unauthorized", ephemeral=True)
    
    await perform_moderation(user_id, action.value, duration)
    await interaction.response.send_message(f"✅ Successfully executed `{action.name}` on ID: {user_id}", ephemeral=True)

@bot.tree.command(name="toggle", description="Turn bridge ON/OFF (Private)")
async def toggle(interaction: discord.Interaction):
    if interaction.user.id != MY_USER_ID:
        await interaction.response.send_message("Unauthorized", ephemeral=True)
        return
    bridge_data["enabled"] = not bridge_data["enabled"]
    status = "ENABLED" if bridge_data["enabled"] else "DISABLED"
    await interaction.response.send_message(f"Bridge is now {status}", ephemeral=True)

# --- EVENTS ---

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id != MY_USER_ID: return
    if payload.channel_id == SOURCE_CHANNEL_ID:
        if payload.message_id in message_map:
            target_msg_id = message_map[payload.message_id]
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                try:
                    original_msg = await target_channel.fetch_message(target_msg_id)
                    await original_msg.add_reaction(payload.emoji)
                except: pass

@bot.event
async def on_message(message):
    if message.author.bot or message.webhook_id: return
    await bot.process_commands(message) # Required to process the !sync command
    
    if not bridge_data["enabled"]: return

    bridge_data["latest_msg"] = {
        "id": message.id, "author": message.author.display_name, "content": message.content or "[Media]",
        "avatar": message.author.display_avatar.url, "reactions": [], "time": datetime.now().strftime("%H:%M:%S")
    }

    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel: await target_channel.send(content=message.content)
    elif message.channel.id == TARGET_CHANNEL_ID:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            mirrored_msg = await webhook.send(content=message.content, username=message.author.display_name, avatar_url=message.author.display_avatar.url, wait=True)
            message_map[mirrored_msg.id] = message.id

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    token = os.environ.get("DISCORD_TOKEN")
    if token: bot.run(token)
