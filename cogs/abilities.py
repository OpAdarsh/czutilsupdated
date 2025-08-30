# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import json
import os

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

class Abilities(commands.Cog):
    """A command to look up character abilities."""
    def __init__(self, bot):
        self.bot = bot
        self.abilities = load_json_data('abilities.json')

    @commands.command(name='abilities', help="!abilities [name] - Look up an ability.", category="Reference")
    async def abilities(self, ctx, *, ability_name: str = None):
        if not self.abilities:
            return await ctx.send("Ability data is currently unavailable.")

        if ability_name:
            # Find the ability (case-insensitive)
            found_ability = next((name for name in self.abilities if name.lower() == ability_name.lower()), None)
            if found_ability:
                data = self.abilities[found_ability]
                embed = discord.Embed(title=f"✨ {found_ability}", description=data['description'], color=discord.Color.teal())
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Could not find an ability named `{ability_name}`.")
        else:
            # Show a list of all abilities
            embed = discord.Embed(title="✨ All Abilities", description="A list of all available abilities in the game.", color=discord.Color.teal())
            ability_list = "\n".join(sorted(self.abilities.keys()))
            embed.description = ability_list
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Abilities(bot))
