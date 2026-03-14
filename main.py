import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os

# --- FLASK WEB SERVER (For Render/UptimeRobot) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is active!"

def run():
    # Render provides the PORT variable automatically
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT CONFIG ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True # Helps with resolving mentions

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ENVIRONMENT VARIABLES ---
# These will be set in the Render Dashboard
MY_USER_ID = int(os.environ.get("MY_USER_ID", 0))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", 0))

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_message(message):
    # 1. Ignore bot's own messages
    if message.author == bot.user:
        return

    # 2. Forward DMs from YOU to the Server
    if isinstance(message.channel, discord.DMChannel) and message.author.id == MY_USER_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        
        if target_channel:
            # Handle Attachments (Images/Files)
            files = []
            for attachment in message.attachments:
                # Convert the attachment into a discord.File object to re-upload it
                files.append(await attachment.to_file())

            # Send the message. 
            # mentions are handled automatically by Discord if the string contains <@ID>
            await target_channel.send(content=message.content, files=files)
            
            # Simple checkmark reaction so you know it worked
            await message.add_reaction("✅")
        else:
            print("Error: Target channel not found. Check your TARGET_CHANNEL_ID.")

    # Allow other commands to work
    await bot.process_commands(message)

# --- EXECUTION ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Missing DISCORD_TOKEN environment variable.")
