# main.py
import discord
from discord.ext import commands
import os
import json
import asyncio
from collections import defaultdict
import database as db

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
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(PREFIX), 
    intents=intents, 
    help_command=None
)

bot.config = config 

COGS_EMOJIS = {
    # Admin is hidden from the public menu
    'Utils': '⚙️',
    'Game': '🎮',
    'CZ': '⚔️'
}

# --- Helper function for creating and sending a cog-specific help embed ---
async def send_cog_help(destination, cog):
    """Creates and sends an embed with the commands of a specific cog."""
    
    if cog.qualified_name == 'CZ':
        embed = discord.Embed(
            title=f"{COGS_EMOJIS.get(cog.qualified_name, '❓')} {cog.qualified_name} Commands",
            description=f"Commands for the **{cog.qualified_name}** game:",
            color=discord.Color.red()
        )
        
        categorized_commands = defaultdict(list)
        for command in sorted(cog.get_commands(), key=lambda cmd: cmd.name):
            category = getattr(command, 'category', 'Uncategorized')
            categorized_commands[category].append(command)
        
        category_order = ["Fun", "Economic", "Team", "Shop", "Battle", "Market"]
        
        for category in category_order:
            if category in categorized_commands:
                command_list = sorted(categorized_commands[category], key=lambda cmd: cmd.name)
                command_text = ""
                for command in command_list:
                    aliases = f"| {', '.join(command.aliases)}" if command.aliases else ""
                    help_desc = command.help.split('-')[1].strip() if '-' in command.help else command.help
                    command_text += f"`{PREFIX}{command.name} {aliases}` - {help_desc}\n"
                embed.add_field(name=f"**{category}**", value=command_text, inline=False)
    
    else:
        embed = discord.Embed(
            title=f"{COGS_EMOJIS.get(cog.qualified_name, '❓')} {cog.qualified_name} Commands",
            description=f"Commands for the **{cog.qualified_name}** cog:",
            color=discord.Color.blue()
        )
        for command in sorted(cog.get_commands(), key=lambda cmd: cmd.name):
            aliases = f"| {', '.join(command.aliases)}" if command.aliases else ""
            embed.add_field(
                name=f"`{PREFIX}{command.name} {aliases}`",
                value=command.help or "No description provided.",
                inline=False
            )
    
    if isinstance(destination, discord.Message):
        await destination.edit(embed=embed)
    else:
        await destination.send(embed=embed)

@bot.command(name='help', description="Shows the list of available commands.")
async def help_command(ctx, *, cog_name: str = None):
    """Shows the list of available commands, paginated by cog with reactions."""
    if cog_name:
        # --- Special Handling for Admin Help ---
        if cog_name.lower() == 'admin':
            admin_id_str = bot.config.get('ADMIN_ID')
            try:
                is_admin = ctx.author.id == int(admin_id_str)
            except (ValueError, TypeError):
                is_admin = False

            if is_admin:
                admin_cog = bot.get_cog('Admin')
                if admin_cog and hasattr(admin_cog, 'get_admin_help_embed'):
                    embed = admin_cog.get_admin_help_embed()
                    await ctx.author.send(embed=embed) # Sends to DM for privacy
                    await ctx.message.add_reaction('✅')
                else:
                    await ctx.send("The Admin cog seems to be missing its help function.")
                return

        cog = bot.get_cog(cog_name.title())
        if cog and cog.qualified_name in COGS_EMOJIS:
            await send_cog_help(ctx, cog)
        else:
            await ctx.send("That cog was not found.")
        return

    help_embed = discord.Embed(
        title="Help Menu",
        description="React with the emojis below to see commands for each category:",
        color=discord.Color.blue()
    )
    
    for cog in bot.cogs.values():
        if cog.qualified_name in COGS_EMOJIS:
            help_embed.add_field(
                name=f"{COGS_EMOJIS[cog.qualified_name]} {cog.qualified_name}",
                value=f"`{len(cog.get_commands())}` commands",
                inline=True
            )
    
    message = await ctx.send(embed=help_embed)
    for emoji in COGS_EMOJIS.values():
        await message.add_reaction(emoji)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or not reaction.message.embeds or reaction.message.embeds[0].title != "Help Menu":
        return
    
    try:
        await reaction.message.remove_reaction(reaction.emoji, user)
    except discord.errors.Forbidden:
        pass
    
    for cog_name, emoji in COGS_EMOJIS.items():
        if str(reaction.emoji) == emoji:
            cog = bot.get_cog(cog_name)
            if cog:
                await send_cog_help(reaction.message, cog)
                return

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    db.init_db() # Initialize database on startup
    
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"✅ Loaded cog: {filename[:-3]}")
            except Exception as e:
                print(f"❌ Failed to load cog {filename[:-3]}: {e}")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"for {PREFIX}help"
        )
    )
    print("✅ Bot is ready!")

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

