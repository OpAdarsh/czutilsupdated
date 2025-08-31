import discord
from discord.ext import commands
import os
import json
import asyncio
from flask import Flask
import threading

# --- Configuration Loading ---
def load_config():
    """Loads bot configuration from config.json at startup."""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading config.json: {e}")
        exit()

config = load_config()
TOKEN = os.getenv('DISCORD_TOKEN') or config.get('TOKEN')
PREFIX = config.get('PREFIX')

if not TOKEN or not PREFIX:
    print("❌ 'TOKEN' must be set as environment variable DISCORD_TOKEN or in config.json, and 'PREFIX' must be set in config.json.")
    exit()

# --- Bot Setup ---
# Define the necessary intents for the bot to function correctly.
# members is for user data, message_content is for reading commands and confirmations.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# We remove the default help command because we have a custom one in a cog.
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(PREFIX), 
    intents=intents, 
    help_command=None
)

# Attach config to the bot object for easy access in cogs
bot.config = config

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def alive():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Status</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                text-align: center; 
                margin-top: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
            }
            .status-box {
                background: rgba(255,255,255,0.1);
                padding: 40px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }
            h1 { 
                font-size: 3em; 
                margin-bottom: 20px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .pulse {
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="status-box">
            <h1 class="pulse">🤖 I'm Alive!</h1>
            <p>Discord Bot is running successfully</p>
            <p>✅ All systems operational</p>
        </div>
    </body>
    </html>
    '''

def run_flask():
    """Run Flask server in a separate thread."""
    import logging
    # Disable Flask's default logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=5000, debug=False) 

@bot.event
async def on_ready():
    """Called when the bot is ready and has connected to Discord."""
    print(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    
    # Initialize database before loading cogs
    import database as db
    db.init_db()
    
    # --- Cog Loading ---
    # Automatically load all .py files from the 'cogs' directory.
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                cog_name = f'cogs.{filename[:-3]}'
                await bot.load_extension(cog_name)
                print(f"✅ Loaded cog: {cog_name}")
            except Exception as e:
                print(f"❌ Failed to load cog {cog_name}: {e}")
    
    # Set the bot's presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"for {PREFIX}help"
        )
    )
    print("✅ Bot is ready!")

async def main():
    """Main async function to start the bot."""
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Web server started on http://0.0.0.0:5000")
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

