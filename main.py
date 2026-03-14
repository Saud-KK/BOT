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
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT CONFIG ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# --- CONFIGURATION ---
MY_USER_ID = 123456789012345678  # Replace with YOUR User ID
TARGET_CHANNEL_ID = 987654321098765432  # Replace with the Server Channel ID

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_message(message):
    # 1. Ignore the bot's own messages
    if message.author == bot.user:
        return

    # 2. Only proceed if the message is a DM AND it's from YOU
    if isinstance(message.channel, discord.DMChannel) and message.author.id == MY_USER_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        
        if target_channel:
            # Sends only the text content with no user labels
            await target_channel.send(message.content)
            
            # Optional: Simple reaction to let you know it sent
            await message.add_reaction("📤")
        else:
            print("Error: Target channel not found.")

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
