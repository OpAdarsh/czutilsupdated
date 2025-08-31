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
        embed = discord.Embed(title="🛒 Item Shop", description="Welcome to the shop! Use `!shop buy <item> [amount]` to purchase.", color=discord.Color.gold())
        embed.add_field(name="📦 Item Box", value="**Cost:** 200 coins each\n**Aliases:** `itembox`, `box`\nA mysterious box containing a random item.", inline=False)
        embed.add_field(name="🎟️ Pull Ticket", value="**Cost:** 50 coins each\n**Aliases:** `ticket`, `tk`\nAllows you to pull a character without cooldown.\n**Bulk:** `!shop buy tk 5` for 5 tickets", inline=False)
        await ctx.send(embed=embed)

    @shop.command(name='buy', help="!shop buy <item> [amount] - Buy an item from the shop.", category="Shop")
    @has_accepted_rules()
    async def buy(self, ctx, item: str, amount: int = 1):
        player = db.get_player(ctx.author.id)
        item_lower = item.lower()
        
        if amount <= 0:
            await ctx.send("Amount must be a positive number!"); return
        
        if item_lower in ['itembox', 'item box', 'box']:
            total_cost = 200 * amount
            if player['coins'] < total_cost:
                await ctx.send(f"You don't have enough coins! (Need {total_cost} for {amount} Item Box{'es' if amount > 1 else ''})"); return
                
            player['coins'] -= total_cost
            items_received = []
            
            for _ in range(amount):
                rarity = random.choices(["common", "rare", "epic", "legendary"], [65, 25, 9.5, 0.5], k=1)[0]
                item_type = random.choice(list(self.items.keys()))
                item_full_name = f"{item_type} {rarity}"
                player['inventory'][item_full_name] = player['inventory'].get(item_full_name, 0) + 1
                items_received.append(item_full_name)
            
            db.update_player(ctx.author.id, player)
            
            if amount == 1:
                await ctx.send(f"You bought an Item Box and found a **{items_received[0]}**!")
            else:
                await ctx.send(f"You bought {amount} Item Boxes and found:\n" + "\n".join(f"• **{item}**" for item in items_received))
            
        elif item_lower in ['ticket', 'pull ticket', 'pullticket', '🎟️', 'pull', 'tk']:
            total_cost = 50 * amount
            if player['coins'] < total_cost:
                await ctx.send(f"You don't have enough coins! (Need {total_cost} for {amount} Pull Ticket{'s' if amount > 1 else ''})"); return
                
            player['coins'] -= total_cost
            player['inventory']['🎟️ Pull Ticket'] = player['inventory'].get('🎟️ Pull Ticket', 0) + amount
            db.update_player(ctx.author.id, player)
            
            if amount == 1:
                await ctx.send(f"You bought a **🎟️ Pull Ticket**! Use `!pull` to bypass the cooldown.")
            else:
                await ctx.send(f"You bought **{amount} 🎟️ Pull Tickets**! Use `!pull` to bypass the cooldown.")
            
        else:
            await ctx.send("That item isn't in the shop. Available items: `itembox`, `ticket` (alias: `tk`)"); return

    @commands.command(name='buy', help="!buy <item> [amount] - Buy an item directly.", category="Shop")
    @has_accepted_rules()
    async def buy_direct(self, ctx, item: str, amount: int = 1):
        await self.buy(ctx, item, amount)

async def setup(bot):
    await bot.add_cog(Shop(bot))
