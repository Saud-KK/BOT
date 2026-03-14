import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os
import aiohttp # Required for Webhooks

# --- FLASK WEB SERVER ---
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

# --- CONFIG FROM ENVIRONMENT ---
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

@bot.event
async def on_ready():
    print(f'Bridge Active as {bot.user.name}')

@bot.event
async def on_message(message):
    # 1. Ignore the bot and webhooks to prevent loops
    if message.author.bot or message.webhook_id:
        return

    # 2. Check if message is in the Source Channel
    if message.channel.id == SOURCE_CHANNEL_ID:
        await forward_to_webhook(message)

    # 3. Two-Way: Check if message is in Target Channel (to send back)
    elif message.channel.id == TARGET_CHANNEL_ID:
        # For the "Two-Way" part, we'll send it back to the source channel
        source_channel = bot.get_channel(SOURCE_CHANNEL_ID)
        if source_channel:
            # We use a standard message here to avoid needing two webhooks
            content = f"**{message.author.display_name}**: {message.content}"
            files = [await a.to_file() for a in message.attachments]
            await source_channel.send(content=content, files=files)

    await bot.process_commands(message)

async def forward_to_webhook(message):
    """Sends the message to the target server using a Webhook."""
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
        
        # Prepare attachments
        files = [await a.to_file() for a in message.attachments]
        
        # Send via Webhook (Impersonates the sender)
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
