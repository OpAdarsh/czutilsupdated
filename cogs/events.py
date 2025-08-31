
import discord
from discord.ext import commands
import json
import os
import random
import time
import datetime
from collections import defaultdict
import asyncio
import math
# Import the database functions
import database as db

# --- Helper for loading static game data ---
def load_json_data(filename):
    """Helper function to load data from a JSON file."""
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: {filename} not found or is improperly formatted.")
        return {}

# --- Custom Check for Rules Acceptance ---
def has_accepted_rules():
    """A custom check to see if a player has accepted the game rules."""
    async def predicate(ctx):
        player = db.get_player(ctx.author.id)
        if player.get("rules_accepted", 0) == 1:
            return True

        cz_cog = ctx.bot.get_cog('Core Gameplay')
        if not cz_cog or ctx.author.id in cz_cog.rules_prompts:
            return False

        embed = discord.Embed(
            title="⚔️ Welcome to the CZ Game! ⚔️",
            description="Before you begin your adventure, you must accept the rules.",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="📜 Game Rules & Info",
            value=(
                "**1. Be Respectful:** All interactions should be friendly.\n"
                "**2. Fair Play:** Do not exploit bugs to gain an unfair advantage.\n"
                "**3. Economy:** Use `!pull` to collect characters, `!daily` for coins, and `!shop` to buy items.\n"
                "**4. Leveling:** `!select` a character to gain XP passively as you chat.\n"
                "**5. Battling:** Form a team with `!team` and challenge others with `!battle`!\n\n"
                "React with ✅ to accept these rules and start your journey."
            ),
            inline=False
        )
        embed.set_footer(text="Once you accept, you won't see this message again.")

        prompt_message = await ctx.send(embed=embed)
        await prompt_message.add_reaction('✅')
        
        cz_cog.rules_prompts[prompt_message.id] = ctx.author.id
        
        await ctx.send("Please accept the rules above to continue.", delete_after=10)
        return False

    return commands.check(predicate)

class Events(commands.Cog, name="Events"):
    """Commands for special events and seasonal activities."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='events', help="!events - Shows current and upcoming events.", category="Events")
    @has_accepted_rules()
    async def events(self, ctx):
        embed = discord.Embed(
            title="🎉 Events",
            description="Currently no active events. Stay tuned for future events!",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="📅 Upcoming Events",
            value="Future events will be announced here!\n\nPossible event types:\n• Double XP weekends\n• Special character banners\n• Bonus coin events\n• Limited-time challenges",
            inline=False
        )
        embed.set_footer(text="Events will provide unique rewards and bonuses!")
        await ctx.send(embed=embed)

    # Example placeholder commands for future events
    # Uncomment and modify these when implementing actual events
    
    # @commands.command(name='eventshop', help="!eventshop - Special event shop.", category="Events")
    # @has_accepted_rules()
    # async def event_shop(self, ctx):
    #     await ctx.send("🎪 Event shop is currently closed. Check back during active events!")
    
    # @commands.command(name='raid', help="!raid - Participate in raid events.", category="Events")
    # @has_accepted_rules()
    # async def raid(self, ctx):
    #     await ctx.send("⚔️ No active raid events. Keep an eye out for announcements!")

async def setup(bot):
    await bot.add_cog(Events(bot))
