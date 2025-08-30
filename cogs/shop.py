# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import json
import os
import random
from collections import defaultdict
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
        await ctx.send("You must accept the rules first. The rules prompt will be shown on your next command.")
        return False
    return commands.check(predicate)

class Shop(commands.Cog):
    """Commands for purchasing items."""
    def __init__(self, bot):
        self.bot = bot
        self.items = load_json_data('items.json')

    @commands.group(name='shop', invoke_without_command=True, help="!shop - Displays the item shop.", category="Shop")
    @has_accepted_rules()
    async def shop(self, ctx):
        embed = discord.Embed(title="🛒 Item Shop", description="Welcome to the shop! Use `!shop buy <item>` to purchase.", color=discord.Color.gold())
        embed.add_field(name="Item Box", value="**Cost:** 200 coins\nA mysterious box containing a random item.", inline=False)
        await ctx.send(embed=embed)

    @shop.command(name='buy', help="!shop buy itembox - Buy an item box.", category="Shop")
    @has_accepted_rules()
    async def buy(self, ctx, item: str):
        if item.lower() != 'itembox':
            await ctx.send("That item isn't in the shop."); return
        
        player = db.get_player(ctx.author.id)
        if player['coins'] < 200:
            await ctx.send("You don't have enough coins! (Need 200)"); return
            
        player['coins'] -= 200
        rarity = random.choices(["common", "rare", "epic", "legendary"], [65, 25, 9.5, 0.5], k=1)[0]
        item_type = random.choice(list(self.items.keys()))
        item_full_name = f"{item_type} {rarity}"
        player['inventory'][item_full_name] = player['inventory'].get(item_full_name, 0) + 1
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You bought an Item Box and found a **{item_full_name}**!")

async def setup(bot):
    await bot.add_cog(Shop(bot))
