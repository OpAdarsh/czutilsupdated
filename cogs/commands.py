# -*- coding: utf-8 -*-
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
        if not cz_cog:
            return False
        
        # Check if user already has a pending rules prompt
        if ctx.author.id in cz_cog.rules_prompts.values():
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

class CharacterManagement(commands.Cog, name="Player Commands"):
    """Commands for economy, character management, and information."""
    def __init__(self, bot):
        self.bot = bot
        self.characters = load_json_data('characters.json')
        self.attacks = load_json_data('attacks.json')
        self.items = load_json_data('items.json')

    async def _find_character_from_input(self, ctx, player_data, identifier):
        """Finds a unique character from a player's collection by ID or name."""
        if identifier.isdigit():
            char_id = int(identifier)
            if char_id in player_data['characters']:
                return char_id
            else:
                await ctx.send(f"❌ No character found in your collection with ID `{char_id}`."); return None

        matches = []
        for char_id, char_data in player_data['characters'].items():
            if identifier.lower() in char_data['name'].lower():
                matches.append((char_id, char_data))

        if not matches:
            await ctx.send(f"❌ No character found in your collection with the name `{identifier}`."); return None
        
        if len(matches) == 1:
            return matches[0][0]

        id_list = ", ".join(f"`{cid}` ({c['name']})" for cid, c in matches)
        await ctx.send(f"❓ You have multiple characters matching that name. Please be more specific or use one of these IDs: {id_list}"); return None

    @commands.command(name='pull', aliases=['p'], help="!pull - Get a free random character every 5 minutes.", category="Gacha System")
    @has_accepted_rules()
    async def pull(self, ctx):
        cz_cog = self.bot.get_cog('Core Gameplay')
        stats_cog = self.bot.get_cog('Stat Calculations')
        if not cz_cog or not stats_cog:
            await ctx.send("Game systems are currently offline. Please try again later."); return

        player = db.get_player(ctx.author.id)
        
        # Check for tickets to bypass cooldown
        has_ticket = player['inventory'].get('🎟️ Pull Ticket', 0) > 0
        cooldown = 300  # 5 minutes
        time_since_last_pull = time.time() - player.get('last_pull_time', 0)

        if time_since_last_pull < cooldown and not has_ticket:
            remaining_time = cooldown - time_since_last_pull
            ticket_msg = " Or use a 🎟️ Pull Ticket to bypass the cooldown!" if player['inventory'].get('🎟️ Pull Ticket', 0) > 0 else ""
            await ctx.send(f"You're on cooldown! Please wait {int(remaining_time // 60)}m {int(remaining_time % 60)}s.{ticket_msg}"); return

        # Use ticket if on cooldown
        if time_since_last_pull < cooldown and has_ticket:
            player['inventory']['🎟️ Pull Ticket'] -= 1
            if player['inventory']['🎟️ Pull Ticket'] == 0:
                del player['inventory']['🎟️ Pull Ticket']
            ticket_used = True
        else:
            ticket_used = False

        char_name, char_data = random.choice(list(self.characters.items()))
        base_char = {"name": char_name, **char_data}
        
        new_char_instance = cz_cog._create_character_instance(base_char)
        
        random_level = random.randint(1, 25)
        new_char_instance['level'] = random_level
        
        base_stats = {k: v for k, v in char_data.items() if k in ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']}
        new_char_instance['stats'] = stats_cog._calculate_stats(base_stats, new_char_instance['individual_ivs'], random_level)
        
        char_id = player['next_character_id']
        player['characters'][char_id] = new_char_instance
        player['latest_pull_id'] = char_id
        player['next_character_id'] += 1
        
        # Only update pull time if not using ticket
        if not ticket_used:
            player['last_pull_time'] = time.time()
        
        db.update_player(ctx.author.id, player)
        
        ticket_text = " (🎟️ Ticket used)" if ticket_used else ""
        await ctx.send(f"You pulled a **Lvl {random_level} {char_name}** with **{new_char_instance['iv']}% IV**{ticket_text}! Use `!info latest` to see their stats.")

    @commands.command(name='sell', help="!sell <id_or_name> - Sells a character for coins.", category="Economy")
    @has_accepted_rules()
    async def sell(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return

        if char_id == player.get('selected_character_id'):
            await ctx.send("You cannot sell your currently selected character. Use `!select` to change it first."); return
        team_char_ids = [char_id for char_id in player.get('team', {}).values() if char_id is not None]
        if char_id in team_char_ids:
            await ctx.send("You cannot sell a character that is on your team. Use `!team remove` first."); return

        character_to_sell = player['characters'][char_id]
        sale_price = 10 + (character_to_sell['level'] * 2) + round(character_to_sell['iv'] / 5)
        
        del player['characters'][char_id]
        player['coins'] += sale_price
        
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You sold **{character_to_sell['name']}** for **{sale_price}** coins.")

    @commands.command(name='balance', aliases=['bal'], help="!balance - Check your coin balance.", category="Economy")
    @has_accepted_rules()
    async def balance(self, ctx):
        player = db.get_player(ctx.author.id)
        await ctx.send(f"💰 You have **{player['coins']}** coins.")

    @commands.command(name='daily', help="!daily - Claim your daily coins.", category="Economy")
    @has_accepted_rules()
    async def daily(self, ctx):
        player = db.get_player(ctx.author.id)
        today, today_str = datetime.date.today(), datetime.date.today().isoformat()
        if player['last_daily_date'] == today_str:
            await ctx.send("You have already claimed your daily reward today!"); return
        
        yesterday = today - datetime.timedelta(days=1)
        player['daily_streak'] = player['daily_streak'] + 1 if player['last_daily_date'] == yesterday.isoformat() else 1
        base_reward, bonus = 50, (player['daily_streak'] - 1) * random.randint(10, 20)
        total_reward = min(200, base_reward + bonus)
        
        player['coins'] += total_reward
        player['last_daily_date'] = today_str
        db.update_player(ctx.author.id, player)
        await ctx.send(f"🎉 You claimed **{total_reward}** coins! Your current streak is **{player['daily_streak']}** day(s).")

    @commands.command(name='weekly', help="!weekly - Claim your weekly coins.", category="Economy")
    @has_accepted_rules()
    async def weekly(self, ctx):
        player = db.get_player(ctx.author.id)
        today = datetime.date.today()
        last_weekly = player.get('last_weekly_date')
        
        if last_weekly:
            last_weekly_date = datetime.datetime.strptime(last_weekly, '%Y-%m-%d').date()
            days_since_weekly = (today - last_weekly_date).days
            if days_since_weekly < 7:
                days_remaining = 7 - days_since_weekly
                await ctx.send(f"You can claim your weekly reward in **{days_remaining}** day(s)!"); return
        
        weekly_reward = random.randint(1000, 1500)
        player['coins'] += weekly_reward
        player['last_weekly_date'] = today.isoformat()
        db.update_player(ctx.author.id, player)
        await ctx.send(f"🎁 You claimed your weekly reward of **{weekly_reward}** coins!")

    @commands.command(name='slots', help="!slots <amount> - Play the slot machine.", category="Economy")
    @has_accepted_rules()
    async def slots(self, ctx, amount: int):
        player = db.get_player(ctx.author.id)
        
        if amount < 10:
            await ctx.send("Minimum bet is **10** coins!"); return
        if amount > player['coins']:
            await ctx.send("You don't have enough coins!"); return
        if amount > 1000:
            await ctx.send("Maximum bet is **1000** coins!"); return
        
        # Deduct the bet
        player['coins'] -= amount
        
        # Slot machine symbols and their weights
        symbols = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎', '7️⃣']
        weights = [25, 20, 20, 15, 10, 7, 3]  # Higher chance for lower value symbols
        
        # Generate 3 random symbols
        result = random.choices(symbols, weights=weights, k=3)
        
        # Calculate winnings
        winnings = 0
        if result[0] == result[1] == result[2]:  # Three of a kind
            multipliers = {'🍒': 2, '🍋': 3, '🍊': 4, '🍇': 5, '🔔': 8, '💎': 15, '7️⃣': 50}
            winnings = amount * multipliers.get(result[0], 2)
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:  # Two of a kind
            winnings = int(amount * 0.5)
        
        player['coins'] += winnings
        db.update_player(ctx.author.id, player)
        
        result_display = " | ".join(result)
        embed = discord.Embed(title="🎰 Slot Machine", color=discord.Color.gold())
        embed.add_field(name="Result", value=f"[ {result_display} ]", inline=False)
        
        if winnings > 0:
            profit = winnings - amount
            if profit > 0:
                embed.add_field(name="🎉 You Won!", value=f"**+{profit}** coins (Total: {winnings})", inline=False)
                embed.color = discord.Color.green()
            else:
                embed.add_field(name="💔 You Lost", value=f"**-{amount - winnings}** coins", inline=False)
                embed.color = discord.Color.red()
        else:
            embed.add_field(name="💔 You Lost", value=f"**-{amount}** coins", inline=False)
            embed.color = discord.Color.red()
        
        embed.add_field(name="Balance", value=f"💰 {player['coins']} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='allcharacters', aliases=['chars', 'characters'], help="!allcharacters [sort_key] - View all characters.", category="Gacha System")
    @has_accepted_rules()
    async def allcharacters(self, ctx, sort_by: str = "name"):
        valid_sorts = ['atk', 'def', 'spd', 'sp_atk', 'sp_def', 'hp', 'name']
        sort_key = sort_by.lower()
        if sort_key not in valid_sorts:
            await ctx.send(f"Invalid sort key. Use one of: `{'`, `'.join(valid_sorts)}`"); return
        
        char_list = list(self.characters.items())
        sorted_chars = sorted(char_list, key=lambda i: i[0]) if sort_key == 'name' else sorted(char_list, key=lambda i: i[1].get(sort_key.upper(), 0), reverse=True)
        
        pages = [sorted_chars[i:i + 10] for i in range(0, len(sorted_chars), 10)]
        current_page = 0

        def create_embed(page_num):
            embed = discord.Embed(title=f"All Characters (Sorted by {sort_key.upper()})", description=f"Page {page_num + 1}/{len(pages)}", color=discord.Color.dark_teal())
            for name, stats in pages[page_num]:
                embed.add_field(name=name, value=f"`ATK:{stats['ATK']}|DEF:{stats['DEF']}|SPD:{stats['SPD']}|SP_ATK:{stats['SP_ATK']}|SP_DEF:{stats['SP_DEF']}|HP:{stats['HP']}`", inline=False)
            return embed

        message = await ctx.send(embed=create_embed(current_page))
        await message.add_reaction('◀️'); await message.add_reaction('▶️')

        def check(r, u): return u == ctx.author and str(r.emoji) in ['◀️', '▶️'] and r.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < len(pages) - 1: current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0: current_page -= 1
                await message.edit(embed=create_embed(current_page)); await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions(); break

    @commands.command(name='info', aliases=['i'], help="!info [latest|id_or_name] - Shows info for a character.", category="Player Info")
    @has_accepted_rules()
    async def info(self, ctx, *, identifier: str = "latest"):
        stats_cog = self.bot.get_cog('Stat Calculations')
        cz_cog = self.bot.get_cog('Core Gameplay')
        if not stats_cog or not cz_cog:
            await ctx.send("Game systems are currently offline."); return
            
        player = db.get_player(ctx.author.id)
        if identifier.lower() == 'latest':
            char_id = player.get('latest_pull_id')
            if char_id is None:
                await ctx.send("You haven't pulled any characters yet."); return
        else:
            char_id = await self._find_character_from_input(ctx, player, identifier)
            if char_id is None: return

        char = player['characters'][char_id]
        display_stats = stats_cog.get_character_display_stats(char)

        embed = discord.Embed(title=f"{char['name']} (ID: {char_id}, IV: {char['iv']}%)", description=char['description'], color=discord.Color.blue())
        xp_needed = cz_cog._get_xp_for_next_level(char['level'])
        
        stats_text = f"**Lvl:** {char['level']} ({char['xp']}/{xp_needed} XP)\n"
        for stat, value in display_stats.items():
            iv_value = char.get('individual_ivs', {}).get(stat, 0)
            stats_text += f"**{stat.upper()}:** {value} (IV: {iv_value}/31)\n"
        
        embed.add_field(name="Stats", value=stats_text, inline=False)
        embed.add_field(name="Ability", value=char['ability'], inline=True)
        embed.add_field(name="Equipped", value=char.get('equipped_item', "None"), inline=True)
        embed.set_footer(text=f"Total IV: {char['iv']}%")
        await ctx.send(embed=embed)

    @commands.command(name='infolatest', aliases=['il'], help="!infolatest - Shows info for your latest pulled character.", category="Player Info")
    @has_accepted_rules()
    async def info_latest(self, ctx):
        # Call the info command with "latest" as argument
        await self.info(ctx, identifier="latest")
            
    @commands.command(name='collection', aliases=['col'], help="!collection - View your character collection.", category="Player Info")
    @has_accepted_rules()
    async def collection(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['characters']:
            await ctx.send("Your collection is empty!"); return
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Collection", color=discord.Color.purple())
        team_char_ids = [char_id for char_id in player.get('team', {}).values() if char_id is not None]
        desc = "".join([f"`{cid}`: **Lvl {c['level']} {c['name']}** ({c['iv']}% IV) {'🛡️' if cid in team_char_ids else ''}{'⭐' if cid == player.get('selected_character_id') else ''}\n" for cid, c in player['characters'].items()])
        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(name='inventory', aliases=['inv'], help="!inventory - View your items.", category="Player Info")
    @has_accepted_rules()
    async def inventory(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['inventory']:
            await ctx.send("Your inventory is empty."); return
        embed = discord.Embed(title="Your Inventory", color=discord.Color.orange())
        
        # Format items with special handling for tickets
        inventory_text = []
        for name, count in player['inventory'].items():
            if "Pull Ticket" in name or "🎟️" in name:
                inventory_text.append(f"🎟️ **Pull Tickets**: x{count}")
            else:
                inventory_text.append(f"**{name}**: x{count}")
        
        embed.description = "\n".join(inventory_text)
        await ctx.send(embed=embed)

    @commands.command(name='items', aliases=['item'], help="!items [item_name] - Shows available items or specific item info.", category="Gacha System")
    @has_accepted_rules()
    async def items(self, ctx, *, item_name: str = None):
        if item_name is None:
            # Show all available items
            embed = discord.Embed(title="📦 Available Items", description="Use `!items <item_name>` for detailed info", color=discord.Color.gold())
            
            for item_type, rarities in self.items.items():
                rarity_list = []
                for rarity in rarities.keys():
                    rarity_list.append(f"{rarity.title()}")
                embed.add_field(name=f"**{item_type}**", value=" | ".join(rarity_list), inline=False)
            
            embed.set_footer(text="Items boost stats when equipped to characters")
            await ctx.send(embed=embed)
        else:
            # Show specific item details
            item_name_lower = item_name.lower()
            found_item = None
            found_type = None
            
            # Search for the item
            for item_type, rarities in self.items.items():
                if item_name_lower in item_type.lower():
                    found_type = item_type
                    found_item = rarities
                    break
            
            if not found_item:
                await ctx.send(f"❌ Item '{item_name}' not found. Use `!items` to see all available items."); return
            
            embed = discord.Embed(title=f"📦 {found_type}", description="Stat boost item that can be equipped to characters", color=discord.Color.blue())
            
            for rarity, data in found_item.items():
                boost_stat = data['stat']
                boost_amount = data['boost']
                embed.add_field(
                    name=f"{rarity.title()} {found_type}", 
                    value=f"**Boosts:** {boost_stat} by +{boost_amount}%\n**Usage:** Equip to character with `!equip <character>, {rarity} {found_type}`", 
                    inline=False
                )
            
            embed.set_footer(text="Get items from Item Boxes in the shop!")
            await ctx.send(embed=embed)

    @commands.command(name='select', help="!select <id_or_name> - Select your active character.", category="Gacha System")
    @has_accepted_rules()
    async def select(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return

        # Ensure char_id is integer
        char_id = int(char_id)
        player['selected_character_id'] = char_id
        db.update_player(ctx.author.id, player)
        await ctx.send(f"✅ You have selected **{player['characters'][char_id]['name']}** (ID: {char_id}) to gain XP.")

    @commands.group(name='team', aliases=['t'], invoke_without_command=True, help="!team - Manages your 3-slot team.", category="Team Management")
    @has_accepted_rules()
    async def team(self, ctx):
        await self.view_team(ctx)

    @team.command(name='view', aliases=['v'], help="!team view - View your active team.", category="Team Management")
    @has_accepted_rules()
    async def view_team(self, ctx):
        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})
        
        embed = discord.Embed(title="Your Active Team", color=discord.Color.green())
        
        # Always show all 3 slots
        for slot in ['1', '2', '3']:
            char_id = team_slots.get(slot)
            if char_id:
                char_info = player['characters'].get(char_id)
                if char_info:
                    embed.add_field(name=f"Slot {slot}", value=f"**{char_info['name']}** (ID: {char_id})\nLvl {char_info['level']}, IV: {char_info['iv']}%", inline=False)
                else:
                    embed.add_field(name=f"Slot {slot}", value=f"Invalid Character (ID: {char_id})", inline=False)
            else:
                embed.add_field(name=f"Slot {slot}", value="📭 Empty Position\n*Use `!team add {slot} <character>` to fill*", inline=False)
                
        await ctx.send(embed=embed)

    @team.command(name='add', help="!team add <slot> <id_or_name> - Adds a character to a team slot.", category="Team Management")
    @has_accepted_rules()
    async def team_add(self, ctx, slot: str, *, identifier: str):
        if slot not in ['1', '2', '3']:
            await ctx.send("Invalid slot. Please choose 1, 2, or 3."); return

        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})

        if team_slots.get(slot) is not None:
            await ctx.send(f"Slot {slot} is already occupied. Use `!team swap` or `!team remove` first."); return
            
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return
        
        # Ensure char_id is integer for consistency
        char_id = int(char_id)
        
        if char_id in team_slots.values():
            await ctx.send("This character is already on your team in another slot."); return

        team_slots[slot] = char_id
        player['team'] = team_slots
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Added **{player['characters'][char_id]['name']}** to team slot {slot}.")
        await self.view_team(ctx)

    @team.command(name='remove', aliases=['r'], help="!team remove <slot> - Removes a character from a team slot.", category="Team Management")
    @has_accepted_rules()
    async def team_remove(self, ctx, slot: str):
        if slot not in ['1', '2', '3']:
            await ctx.send("Invalid slot. Please choose 1, 2, or 3."); return
            
        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})
        
        char_id = team_slots.get(slot)
        if char_id is None:
            await ctx.send(f"Slot {slot} is already empty."); return
            
        char_name = player['characters'][char_id]['name']
        team_slots[slot] = None
        player['team'] = team_slots
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Removed **{char_name}** from team slot {slot}.")
        await self.view_team(ctx)

    @team.command(name='swap', help="!team swap <slot> <id_or_name> - Swaps a character into a team slot.", category="Team Management")
    @has_accepted_rules()
    async def team_swap(self, ctx, slot: str, *, identifier: str):
        if slot not in ['1', '2', '3']:
            await ctx.send("Invalid slot. Please choose 1, 2, or 3."); return
            
        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})

        char_id_to_add = await self._find_character_from_input(ctx, player, identifier)
        if char_id_to_add is None: return
        
        # Ensure char_id is integer for consistency
        char_id_to_add = int(char_id_to_add)

        # Check if the character is already in another slot
        current_slot_of_char = None
        for s, c_id in team_slots.items():
            if c_id == char_id_to_add:
                current_slot_of_char = s
                break
        
        # Swap logic
        char_currently_in_target_slot = team_slots.get(slot)
        
        if current_slot_of_char:
            team_slots[current_slot_of_char] = char_currently_in_target_slot
            team_slots[slot] = char_id_to_add
            await ctx.send(f"Swapped characters in slot {current_slot_of_char} and {slot}.")
        else: # Just add to the slot (and remove the old one)
            team_slots[slot] = char_id_to_add
            await ctx.send(f"Placed **{player['characters'][char_id_to_add]['name']}** into team slot {slot}.")

        player['team'] = team_slots
        db.update_player(ctx.author.id, player)
        await self.view_team(ctx)

    @commands.command(name='equip', aliases=['eq'], help="!equip <id_or_name>, <item_name> - Equips an item.", category="Team Management")
    @has_accepted_rules()
    async def equip(self, ctx, *, arguments: str):
        try:
            identifier, item_name = [arg.strip() for arg in arguments.split(',', 1)]
        except ValueError:
            await ctx.send("Invalid format. Use: `!equip <character>, <item_name>`"); return

        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return
        
        item_name_lower = item_name.lower()
        found_item = next((inv_item for inv_item in player['inventory'] if item_name_lower == inv_item.lower()), None)
        if not found_item or player['inventory'].get(found_item, 0) == 0:
            await ctx.send(f"You don't have an item named '{item_name}'."); return
            
        character = player['characters'][char_id]
        if character['equipped_item']:
            await ctx.send(f"**{character['name']}** already has an item equipped. Unequip it first."); return
        
        character['equipped_item'] = found_item
        player['inventory'][found_item] -= 1
        if player['inventory'][found_item] == 0: del player['inventory'][found_item]
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Equipped **{found_item}** on **{character['name']}**.")

    @commands.command(name='unequip', aliases=['ue'], help="!unequip <id_or_name> - Unequips an item.", category="Team Management")
    @has_accepted_rules()
    async def unequip(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return
        
        character = player['characters'][char_id]
        item_name = character['equipped_item']
        if not item_name:
            await ctx.send(f"**{character['name']}** has no item equipped."); return
            
        character['equipped_item'] = None
        player['inventory'][item_name] = player['inventory'].get(item_name, 0) + 1
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Unequipped **{item_name}** from **{character['name']}**.")

    @commands.group(name='moves', aliases=['m'], invoke_without_command=True, help="!moves [id_or_name] - Manage character moves.", category="Team Management")
    @has_accepted_rules()
    async def moves(self, ctx, *, identifier: str = None):
        player = db.get_player(ctx.author.id)
        if identifier is None:
            char_id = player.get('selected_character_id')
            if not char_id:
                await ctx.send("Please select a character first with `!select <id>` or specify one."); return
        else:
            char_id = await self._find_character_from_input(ctx, player, identifier)
            if char_id is None: return
            
        character = player['characters'][char_id]
        embed = discord.Embed(title=f"Moveset for {character['name']} (Lvl {character['level']})", color=discord.Color.orange())
        
        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        active_moves = character.get('moveset', [None, None, None, None])
        
        # Ensure moveset has 4 slots
        while len(active_moves) < 4:
            active_moves.append(None)
        
        # Display active moveset in 4-slot format
        moveset_display = []
        for i, move_name in enumerate(active_moves, 1):
            if move_name:
                # Find move data
                move_data = next((m for m in self.attacks.get('physical', []) + self.attacks.get('special', []) + all_special_moves if m['name'] == move_name), None)
                if move_data:
                    power = move_data.get('power', 0)
                    accuracy = move_data.get('accuracy', 100)
                    move_type = move_data.get('type', 'N/A')
                    moveset_display.append(f"**{i}.** {move_name} - Power: {power}, Acc: {accuracy}%, Type: {move_type}")
                else:
                    moveset_display.append(f"**{i}.** {move_name} - (Data not found)")
            else:
                moveset_display.append(f"**{i}.** *Empty Slot* - Use `!learn` to fill")
        
        embed.add_field(name="⚔️ Active Moveset (4 Slots)", value="\n".join(moveset_display), inline=False)

        active_moves_names = [move for move in active_moves if move is not None]
        unlocked_and_inactive = [f"**{m['name']}** - Power: {m.get('power', 0)}, Acc: {m.get('accuracy', 100)}%"
                                for m in all_special_moves
                                if m['unlock_level'] <= character['level'] and m['name'] not in active_moves_names]
        if unlocked_and_inactive:
            embed.add_field(name="📚 Unlocked (Inactive)", value="\n".join(unlocked_and_inactive), inline=False)
            
        locked_moves = [f"**{m['name']}** (Lvl {m['unlock_level']})"
                        for m in all_special_moves
                        if m['unlock_level'] > character['level']]
        if locked_moves:
            embed.add_field(name="🔒 Locked", value="\n".join(locked_moves), inline=False)

        embed.set_footer(text="Use `!moves swap <id_or_name>, <new_move>, <old_move>` or `!learn <id_or_name>, <move_name>`")
        await ctx.send(embed=embed)

    @moves.command(name='swap', help="!moves swap <id_or_name>, <new>, <old> - Swaps moves.", category="Team Management")
    @has_accepted_rules()
    async def swap_moves(self, ctx, *, arguments: str):
        try:
            identifier, new_move, old_move = [arg.strip() for arg in arguments.split(',', 2)]
        except ValueError:
            await ctx.send("Invalid format. Use: `!moves swap <character>, <new_move>, <old_move>`"); return

        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return

        character = player['characters'][char_id]
        common_move_names = [m['name'].lower() for m in self.attacks.get('physical', []) + self.attacks.get('special', [])]
        old_move_name = next((m for m in character.get('moveset', []) if m.lower() == old_move.lower()), None)
        
        if not old_move_name:
            await ctx.send(f"'{old_move}' is not in your active moveset."); return
        if old_move_name.lower() in common_move_names:
             await ctx.send(f"You cannot swap out a common attack like '{old_move_name}'."); return

        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        new_move_data = next((m for m in all_special_moves if m['name'].lower() == new_move.lower()), None)
        
        if not new_move_data:
            await ctx.send(f"'{new_move}' is not a valid special move for this character."); return
        if character['level'] < new_move_data['unlock_level']:
            await ctx.send(f"You haven't unlocked '{new_move_data['name']}' yet (requires Lvl {new_move_data['unlock_level']})."); return
        if new_move_data['name'] in character.get('moveset', []):
            await ctx.send(f"'{new_move_data['name']}' is already in your active moveset."); return

        try:
            active_moveset = character.get('moveset', [])
            index = active_moveset.index(old_move_name)
            active_moveset[index] = new_move_data['name']
        except ValueError:
             await ctx.send(f"An unexpected error occurred."); return

        character['moveset'] = active_moveset
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Swapped **{old_move_name}** for **{new_move_data['name']}** on {character['name']}!")

    class SlotSelectionView(discord.ui.View):
        def __init__(self, ctx, character, move_data, current_moveset, player):
            super().__init__(timeout=60.0)
            self.ctx = ctx
            self.character = character
            self.move_data = move_data
            self.current_moveset = current_moveset
            self.player = player
            self.char_id = None
            
            # Find character ID
            for cid, char in player['characters'].items():
                if char == character:
                    self.char_id = cid
                    break
            
            # Create buttons for each slot
            for i in range(4):
                current_move = current_moveset[i] if current_moveset[i] else "Empty"
                button = discord.ui.Button(
                    label=f"Slot {i+1}: {current_move}",
                    style=discord.ButtonStyle.secondary if current_moveset[i] else discord.ButtonStyle.success,
                    custom_id=f"slot_{i}"
                )
                button.callback = self.create_slot_callback(i)
                self.add_item(button)
        
        def create_slot_callback(self, slot_index):
            async def slot_callback(interaction: discord.Interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("❌ This isn't your learn command!", ephemeral=True)
                    return
                
                old_move = self.current_moveset[slot_index] if self.current_moveset[slot_index] else "Empty Slot"
                self.current_moveset[slot_index] = self.move_data['name']
                self.character['moveset'] = self.current_moveset
                
                # Update database
                db.update_player(self.ctx.author.id, self.player)
                
                if old_move == "Empty Slot":
                    response = f"✅ **{self.character['name']}** learned **{self.move_data['name']}** in slot {slot_index + 1}!"
                else:
                    response = f"✅ **{self.character['name']}** forgot **{old_move}** and learned **{self.move_data['name']}** in slot {slot_index + 1}!"
                
                await interaction.response.edit_message(content=response, embed=None, view=None)
                self.stop()
            
            return slot_callback
        
        async def on_timeout(self):
            try:
                await self.message.edit(content="⏰ Move learning timed out. Try again when you're ready.", embed=None, view=None)
            except:
                pass

    @commands.command(name='learn', help="!learn <move_name> OR !learn <character>, <move_name> OR !learn <character>, <slot>, <move_name> - Teaches a move to a character.", category="Team Management")
    @has_accepted_rules()
    async def learn_move(self, ctx, *, arguments: str):
        player = db.get_player(ctx.author.id)
        
        # Parse arguments - support multiple formats
        parts = [arg.strip() for arg in arguments.split(',')]
        
        if len(parts) == 3:
            # Format: !learn <character>, <slot>, <move_name>
            identifier, slot_str, move_name = parts
            try:
                target_slot = int(slot_str) - 1  # Convert to 0-based index
                if target_slot < 0 or target_slot > 3:
                    await ctx.send("❌ Slot must be between 1-4!")
                    return
            except ValueError:
                await ctx.send("❌ Invalid slot number. Use: `!learn <character>, <slot 1-4>, <move_name>`")
                return
            
            char_id = await self._find_character_from_input(ctx, player, identifier)
            if char_id is None:
                return
                
        elif len(parts) == 2:
            # Format: !learn <character>, <move_name>
            identifier, move_name = parts
            target_slot = None
            char_id = await self._find_character_from_input(ctx, player, identifier)
            if char_id is None:
                return
                
        elif len(parts) == 1:
            # Format: !learn <move_name> (use selected character)
            move_name = parts[0]
            target_slot = None
            char_id = player.get('selected_character_id')
            if not char_id:
                await ctx.send("❌ No character selected! Use `!select <character>` first, or use `!learn <character>, <move_name>`")
                return
            if char_id not in player['characters']:
                await ctx.send("❌ Your selected character no longer exists! Please select a new one.")
                return
        else:
            await ctx.send("❌ Invalid format. Use:\n• `!learn <move_name>`\n• `!learn <character>, <move_name>`\n• `!learn <character>, <slot 1-4>, <move_name>`")
            return

        # Ensure char_id is integer for consistency
        char_id = int(char_id)
        character = player['characters'][char_id]
        
        # Get all available moves for this character
        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        common_physical = self.attacks.get('physical', [])
        common_special = self.attacks.get('special', [])
        
        # Find the move
        move_data = None
        for move_list in [common_physical, common_special, all_special_moves]:
            move_data = next((m for m in move_list if m['name'].lower() == move_name.lower()), None)
            if move_data:
                break
        
        if not move_data:
            await ctx.send(f"❌ **Error:** Move '{move_name}' not found.")
            return
        
        # Check if it's a special move that requires unlocking
        if move_data in all_special_moves and character['level'] < move_data['unlock_level']:
            await ctx.send(f"❌ **Error:** '{move_data['name']}' requires level {move_data['unlock_level']} to learn (current level: {character['level']}).")
            return
        
        # Check if move is already known
        current_moveset = character.get('moveset', [None, None, None, None])
        if move_data['name'] in current_moveset:
            await ctx.send(f"❌ **{character['name']}** already knows **{move_data['name']}**!")
            return
        
        # If specific slot was requested
        if target_slot is not None:
            old_move = current_moveset[target_slot] if current_moveset[target_slot] else "Empty Slot"
            current_moveset[target_slot] = move_data['name']
            character['moveset'] = current_moveset
            db.update_player(ctx.author.id, player)
            
            if old_move == "Empty Slot":
                await ctx.send(f"✅ **{character['name']}** learned **{move_data['name']}** in slot {target_slot + 1}!")
            else:
                await ctx.send(f"✅ **{character['name']}** forgot **{old_move}** and learned **{move_data['name']}** in slot {target_slot + 1}!")
            return
        
        # Find first empty slot or use UI for selection
        empty_slot = None
        for i, move in enumerate(current_moveset):
            if move is None:
                empty_slot = i
                break
        
        if empty_slot is not None:
            # Learn move in empty slot
            current_moveset[empty_slot] = move_data['name']
            character['moveset'] = current_moveset
            db.update_player(ctx.author.id, player)
            await ctx.send(f"✅ **{character['name']}** learned **{move_data['name']}** in slot {empty_slot + 1}!")
        else:
            # All slots full, show slot selection UI
            embed = discord.Embed(
                title=f"🎯 Learn Move: {move_data['name']}",
                description=f"**{character['name']}'s** moveset is full! Choose which slot to replace:",
                color=discord.Color.orange()
            )
            
            # Show current moveset with move details
            moveset_info = []
            for i, move in enumerate(current_moveset):
                if move:
                    # Find move data for details
                    move_info = None
                    for move_list in [common_physical, common_special, all_special_moves]:
                        move_info = next((m for m in move_list if m['name'] == move), None)
                        if move_info:
                            break
                    
                    if move_info:
                        power = move_info.get('power', 0)
                        accuracy = move_info.get('accuracy', 100)
                        move_type = move_info.get('type', 'Normal')
                        moveset_info.append(f"**{i+1}.** {move} - Power: {power}, Acc: {accuracy}%, Type: {move_type}")
                    else:
                        moveset_info.append(f"**{i+1}.** {move}")
                else:
                    moveset_info.append(f"**{i+1}.** *Empty*")
            
            embed.add_field(name="Current Moveset", value="\n".join(moveset_info), inline=False)
            
            # Show new move details
            new_move_power = move_data.get('power', 0)
            new_move_acc = move_data.get('accuracy', 100)
            new_move_type = move_data.get('type', 'Normal')
            embed.add_field(
                name="New Move", 
                value=f"**{move_data['name']}** - Power: {new_move_power}, Acc: {new_move_acc}%, Type: {new_move_type}", 
                inline=False
            )
            
            view = self.SlotSelectionView(ctx, character, move_data, current_moveset, player)
            message = await ctx.send(embed=embed, view=view)
            view.message = message

async def setup(bot):
    await bot.add_cog(CharacterManagement(bot))

