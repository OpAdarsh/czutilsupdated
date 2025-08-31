# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import json
import os
import random
import time
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
        embed.add_field(name="⚡ XP Booster", value="**1hr:** 40 coins | **6hr:** 80 coins | **12hr:** 100 coins\n**Aliases:** `xpboost`, `xp`\nDoubles XP gain for selected character.", inline=False)
        embed.add_field(name="🧪 Level Potion", value="**Cost:** 100 coins each\n**Aliases:** `potion`, `lvlup`\nInstantly increases selected character's level.\nLow levels: +1-3 levels | High levels: +1 level", inline=False)
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
        
        elif item_lower in ['xpboost', 'xp booster', 'xp', '1hr', '6hr', '12hr']:
            # Check if player has a selected character
            if not player.get('selected_character_id'):
                await ctx.send("❌ You need to select a character first using `!select <character_id>`!"); return
            
            char_id = player['selected_character_id']
            if char_id not in player.get('characters', {}):
                await ctx.send("❌ Your selected character doesn't exist!"); return
                
            # Determine duration and cost
            duration_costs = {'1hr': 40, '6hr': 80, '12hr': 100}
            if item_lower in ['1hr']:
                duration, cost = '1hr', 40
            elif item_lower in ['6hr']:
                duration, cost = '6hr', 80
            elif item_lower in ['12hr']:
                duration, cost = '12hr', 100
            else:
                await ctx.send("❌ Please specify duration: `1hr`, `6hr`, or `12hr`\nExample: `!shop buy 1hr`"); return
            
            total_cost = cost * amount
            if player['coins'] < total_cost:
                await ctx.send(f"You don't have enough coins! (Need {total_cost} for {amount} {duration} XP Booster{'s' if amount > 1 else ''})"); return
            
            player['coins'] -= total_cost
            
            # Add XP booster with expiration time
            import time
            duration_seconds = {'1hr': 3600, '6hr': 21600, '12hr': 43200}[duration]
            expiration_time = time.time() + (duration_seconds * amount)
            
            # Store XP booster info in player data
            if 'xp_booster' not in player:
                player['xp_booster'] = {}
            player['xp_booster'][char_id] = expiration_time
            
            db.update_player(ctx.author.id, player)
            
            character = player['characters'][char_id]
            if amount == 1:
                await ctx.send(f"✅ You bought a **{duration} XP Booster** for **{character['name']}**! XP gain is now doubled for {duration}.")
            else:
                total_hours = amount * int(duration.replace('hr', ''))
                await ctx.send(f"✅ You bought **{amount} {duration} XP Boosters** for **{character['name']}**! XP gain is now doubled for {total_hours} hours total.")
        
        elif item_lower in ['potion', 'level potion', 'lvlup']:
            # Check if player has a selected character
            if not player.get('selected_character_id'):
                await ctx.send("❌ You need to select a character first using `!select <character_id>`!"); return
            
            char_id = player['selected_character_id']
            if char_id not in player.get('characters', {}):
                await ctx.send("❌ Your selected character doesn't exist!"); return
                
            character = player['characters'][char_id]
            if character['level'] >= 100:
                await ctx.send("❌ Your character is already at max level (100)!"); return
            
            total_cost = 100 * amount
            if player['coins'] < total_cost:
                await ctx.send(f"You don't have enough coins! (Need {total_cost} for {amount} Level Potion{'s' if amount > 1 else ''})"); return
            
            player['coins'] -= total_cost
            
            # Calculate level increase based on current level
            levels_gained = 0
            for _ in range(amount):
                if character['level'] >= 100:
                    break
                elif character['level'] < 50:
                    # Low level: 1-3 levels
                    level_increase = random.randint(1, 3)
                else:
                    # High level: only 1 level
                    level_increase = 1
                
                new_level = min(100, character['level'] + level_increase)
                levels_gained += new_level - character['level']
                character['level'] = new_level
            
            # Recalculate stats with new level
            stats_cog = self.bot.get_cog('Stat Calculations')
            cz_cog = self.bot.get_cog('Core Gameplay')
            if stats_cog and cz_cog:
                base_char_data = cz_cog.characters.get(character['name'])
                if base_char_data:
                    character['stats'] = stats_cog._calculate_stats(base_char_data, character['individual_ivs'], character['level'])
            
            db.update_player(ctx.author.id, player)
            
            if amount == 1:
                await ctx.send(f"🧪 You used a **Level Potion** on **{character['name']}**! They gained **{levels_gained} level{'s' if levels_gained != 1 else ''}** and are now level **{character['level']}**!")
            else:
                await ctx.send(f"🧪 You used **{amount} Level Potions** on **{character['name']}**! They gained **{levels_gained} level{'s' if levels_gained != 1 else ''}** total and are now level **{character['level']}**!")
            
        else:
            await ctx.send("That item isn't in the shop. Available items: `itembox`, `ticket` (alias: `tk`), `xpboost` (`1hr`/`6hr`/`12hr`), `potion`"); return

    @commands.command(name='buy', help="!buy <item> [amount] - Buy an item directly.", category="Shop")
    @has_accepted_rules()
    async def buy_direct(self, ctx, item: str, amount: int = 1):
        await self.buy(ctx, item, amount)

async def setup(bot):
    await bot.add_cog(Shop(bot))
