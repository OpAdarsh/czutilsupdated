import discord
from discord.ext import commands
import os
import json
import asyncio

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
TOKEN = config.get('TOKEN')
PREFIX = config.get('PREFIX')

if not TOKEN or not PREFIX:
    print("❌ 'TOKEN' and 'PREFIX' must be set in config.json.")
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

@bot.event
async def on_ready():
    """Called when the bot is ready and has connected to Discord."""
    print(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    
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
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

