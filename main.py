import discord
from discord.ext import commands
import os
import json
import asyncio
from collections import defaultdict

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

CATEGORY_EMOJIS = {
    'Economic': '💰',
    'Team': '🛡️',
    'Shop': '🛒',
    'Battle': '⚔️',
    'Bot Commands': '⚙️'
}

# --- Helper function for creating and sending a category-specific help embed ---
async def send_category_help(destination, category_name):
    """Creates and sends an embed with the commands of a specific category."""
    embed = discord.Embed(
        title=f"{CATEGORY_EMOJIS.get(category_name, '❓')} {category_name} Commands",
        color=discord.Color.blue()
    )
    
    commands_in_category = []
    for cog in bot.cogs.values():
        for command in cog.get_commands():
            if hasattr(command, 'category') and command.category == category_name:
                commands_in_category.append(command)
            elif isinstance(command, commands.Group):
                for sub_command in command.commands:
                    if hasattr(sub_command, 'category') and sub_command.category == category_name:
                         commands_in_category.append(sub_command)
                         
    if category_name == 'Shop':
        shop_group = bot.get_command('shop')
        if shop_group:
            commands_in_category.append(shop_group)
    if category_name == 'Team':
        team_group = bot.get_command('team')
        if team_group:
            commands_in_category.append(team_group)

    if not commands_in_category:
        embed.description = "No commands found in this category."
    else:
        for command in sorted(commands_in_category, key=lambda cmd: cmd.name):
            aliases = f"| {', '.join(command.aliases)}" if command.aliases else ""
            help_desc = command.help.split('-')[1].strip() if '-' in command.help else command.help
            embed.add_field(
                name=f"`{PREFIX}{command.qualified_name} {aliases}`",
                value=help_desc,
                inline=False
            )

    if isinstance(destination, discord.Message):
        await destination.edit(embed=embed)
    else:
        await destination.send(embed=embed)

@bot.command(name='help', description="Shows the list of available commands.")
async def help_command(ctx, *, category_name: str = None):
    """Shows the list of available commands, paginated by category with reactions."""
    # Special handling for Admin help
    if category_name and category_name.lower() == 'admin':
        admin_id_str = bot.config.get('ADMIN_ID')
        try:
            is_admin = ctx.author.id == int(admin_id_str)
        except (ValueError, TypeError):
            is_admin = False

        if is_admin:
            admin_cog = bot.get_cog('Admin')
            if admin_cog and hasattr(admin_cog, 'get_admin_help_embed'):
                embed = admin_cog.get_admin_help_embed()
                await ctx.author.send(embed=embed)
                await ctx.message.add_reaction('✅')
            else:
                await ctx.send("The Admin cog seems to be missing its help function.")
            return

    # If a specific category is requested
    if category_name:
        capitalized_category = category_name.title()
        if capitalized_category in CATEGORY_EMOJIS:
            await send_category_help(ctx, capitalized_category)
        else:
            await ctx.send("That command category was not found.")
        return

    # Show main help menu
    help_embed = discord.Embed(
        title="Help Menu",
        description="React with the emojis below to see commands for each category:",
        color=discord.Color.blue()
    )
    
    for category, emoji in CATEGORY_EMOJIS.items():
        # Count commands in each category
        command_count = 0
        for cog in bot.cogs.values():
            for command in cog.get_commands():
                if hasattr(command, 'category') and command.category == category:
                    command_count += 1
                elif isinstance(command, commands.Group):
                    for sub_command in command.commands:
                        if hasattr(sub_command, 'category') and sub_command.category == category:
                            command_count += 1
        
        # Add special cases for groups that don't have a category on the top-level command
        if category == 'Shop':
            if bot.get_command('shop'): command_count += 1
        if category == 'Team':
            if bot.get_command('team'): command_count += 1

        help_embed.add_field(
            name=f"{emoji} {category}",
            value=f"`{command_count}` commands",
            inline=True
        )
    
    message = await ctx.send(embed=help_embed)
    for emoji in CATEGORY_EMOJIS.values():
        await message.add_reaction(emoji)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or not reaction.message.embeds or reaction.message.embeds[0].title != "Help Menu":
        return
    
    try:
        await reaction.message.remove_reaction(reaction.emoji, user)
    except discord.errors.Forbidden:
        pass
    
    for category_name, emoji in CATEGORY_EMOJIS.items():
        if str(reaction.emoji) == emoji:
            await send_category_help(reaction.message, category_name)
            return

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    # Initialize database on startup
    # db.init_db() is called in a cog now
    
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                cog_name = filename[:-3]
                await bot.load_extension(f'cogs.{cog_name}')
                print(f"✅ Loaded cog: {cog_name}")
                # Set categories for commands after they are loaded
                cog = bot.get_cog(cog_name.title())
                if cog:
                    for command in cog.walk_commands():
                        if not hasattr(command, 'category'):
                            if cog_name.lower() == 'rpg':
                                if command.name in ['pull', 'balance', 'daily', 'allcharacters', 'info', 'collection']: command.category = 'Economic'
                                elif command.name in ['select', 'team', 'equip', 'unequip', 'moves']: command.category = 'Team'
                                elif command.name in ['shop', 'buy']: command.category = 'Shop'
                                elif command.name in ['battle']: command.category = 'Battle'
                            elif cog_name.lower() == 'utils':
                                if command.name in ['afk', 'calculator', 'slots']: command.category = 'Bot Commands'
                            elif cog_name.lower() == 'admin':
                                # Admin is intentionally hidden from the public help menu
                                command.category = 'Admin'

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
