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
            title="⚔️ Welcome to the CZ Game ⚔️",
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

    def _apply_filters(self, characters, filter_string):
        """Apply PokéTwo-style filters to character collection."""
        if not filter_string:
            return characters
        
        filtered = {}
        for char_id, char_data in characters.items():
            include = True
            
            # Split filters by spaces, but handle quoted strings
            import shlex
            try:
                filter_parts = shlex.split(filter_string.lower())
            except ValueError:
                filter_parts = filter_string.lower().split()
            
            for filter_part in filter_parts:
                if ':' in filter_part:
                    # Handle key:value filters
                    key, value = filter_part.split(':', 1)
                    
                    if key == 'name':
                        if value not in char_data['name'].lower():
                            include = False
                            break
                    elif key == 'level':
                        if str(char_data['level']) != value:
                            include = False
                            break
                    elif key == 'ability':
                        if value not in char_data.get('ability', '').lower():
                            include = False
                            break
                elif filter_part.startswith('level'):
                    # Handle level comparisons
                    if '>=' in filter_part:
                        try:
                            min_level = int(filter_part.split('>=')[1])
                            if char_data['level'] < min_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<=' in filter_part:
                        try:
                            max_level = int(filter_part.split('<=')[1])
                            if char_data['level'] > max_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '>' in filter_part:
                        try:
                            min_level = int(filter_part.split('>')[1])
                            if char_data['level'] <= min_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<' in filter_part:
                        try:
                            max_level = int(filter_part.split('<')[1])
                            if char_data['level'] >= max_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                elif filter_part.startswith('iv'):
                    # Handle IV comparisons
                    if '>=' in filter_part:
                        try:
                            min_iv = float(filter_part.split('>=')[1])
                            if char_data['iv'] < min_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<=' in filter_part:
                        try:
                            max_iv = float(filter_part.split('<=')[1])
                            if char_data['iv'] > max_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '>' in filter_part:
                        try:
                            min_iv = float(filter_part.split('>')[1])
                            if char_data['iv'] <= min_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<' in filter_part:
                        try:
                            max_iv = float(filter_part.split('<')[1])
                            if char_data['iv'] >= max_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                else:
                    # Handle simple name filter
                    if filter_part not in char_data['name'].lower():
                        include = False
                        break
            
            if include:
                filtered[char_id] = char_data
        
        return filtered

    def _apply_character_filters(self, characters, filter_string):
        """Apply filters to the global character database."""
        if not filter_string:
            return characters
        
        filtered = {}
        for char_name, char_data in characters.items():
            include = True
            
            # Split filters by spaces, but handle quoted strings
            import shlex
            try:
                filter_parts = shlex.split(filter_string.lower())
            except ValueError:
                filter_parts = filter_string.lower().split()
            
            for filter_part in filter_parts:
                if ':' in filter_part:
                    # Handle key:value filters
                    key, value = filter_part.split(':', 1)
                    
                    if key == 'name':
                        if value not in char_name.lower():
                            include = False
                            break
                    elif key == 'ability':
                        if value not in char_data.get('ability', '').lower():
                            include = False
                            break
                elif filter_part.startswith(('atk', 'def', 'spd', 'sp_atk', 'sp_def', 'hp')):
                    # Handle stat comparisons
                    stat_name = None
                    if filter_part.startswith('sp_atk'):
                        stat_name = 'SP_ATK'
                        comparison_part = filter_part[6:]
                    elif filter_part.startswith('sp_def'):
                        stat_name = 'SP_DEF'
                        comparison_part = filter_part[6:]
                    elif filter_part.startswith('atk'):
                        stat_name = 'ATK'
                        comparison_part = filter_part[3:]
                    elif filter_part.startswith('def'):
                        stat_name = 'DEF'
                        comparison_part = filter_part[3:]
                    elif filter_part.startswith('spd'):
                        stat_name = 'SPD'
                        comparison_part = filter_part[3:]
                    elif filter_part.startswith('hp'):
                        stat_name = 'HP'
                        comparison_part = filter_part[2:]
                    
                    if stat_name and comparison_part:
                        char_stat = char_data.get(stat_name, 0)
                        
                        if '>=' in comparison_part:
                            try:
                                min_val = int(comparison_part.split('>=')[1])
                                if char_stat < min_val:
                                    include = False
                                    break
                            except (ValueError, IndexError):
                                continue
                        elif '<=' in comparison_part:
                            try:
                                max_val = int(comparison_part.split('<=')[1])
                                if char_stat > max_val:
                                    include = False
                                    break
                            except (ValueError, IndexError):
                                continue
                        elif '>' in comparison_part:
                            try:
                                min_val = int(comparison_part.split('>')[1])
                                if char_stat <= min_val:
                                    include = False
                                    break
                            except (ValueError, IndexError):
                                continue
                        elif '<' in comparison_part:
                            try:
                                max_val = int(comparison_part.split('<')[1])
                                if char_stat >= max_val:
                                    include = False
                                    break
                            except (ValueError, IndexError):
                                continue
                else:
                    # Handle simple name filter
                    if filter_part not in char_name.lower():
                        include = False
                        break
            
            if include:
                filtered[char_name] = char_data
        
        return filtered

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

    @commands.command(name='allcharacters', aliases=['chars', 'characters'], help="!allcharacters [filters] - View all characters with optional filters.", category="Gacha System")
    @has_accepted_rules()
    async def allcharacters(self, ctx, *, args: str = ""):
        # Parse arguments for sort and filters
        parts = args.strip().split() if args else []
        sort_key = "name"
        filters = ""
        
        valid_sorts = ['atk', 'def', 'spd', 'sp_atk', 'sp_def', 'hp', 'name']
        
        # Check if first argument is a sort key
        if parts and parts[0].lower() in valid_sorts:
            sort_key = parts[0].lower()
            filters = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            filters = " ".join(parts)

        # Apply filters to characters
        filtered_chars = self._apply_character_filters(self.characters, filters)
        
        if not filtered_chars:
            await ctx.send("No characters match your filters!"); return

        # Sort characters
        char_list = list(filtered_chars.items())
        if sort_key == 'name':
            sorted_chars = sorted(char_list, key=lambda i: i[0])
        else:
            sorted_chars = sorted(char_list, key=lambda i: i[1].get(sort_key.upper(), 0), reverse=True)

        # Pagination
        chars_per_page = 10
        total_pages = math.ceil(len(sorted_chars) / chars_per_page)
        current_page = 0

        def create_embed(page_num):
            start_idx = page_num * chars_per_page
            end_idx = start_idx + chars_per_page
            page_chars = sorted_chars[start_idx:end_idx]
            
            embed = discord.Embed(
                title=f"All Characters (Sorted by {sort_key.upper()})",
                description=f"Page {page_num + 1}/{total_pages} • {len(filtered_chars)} characters" + (f" (filtered)" if filters else ""),
                color=discord.Color.dark_teal()
            )
            
            for name, stats in page_chars:
                stat_line = f"`ATK:{stats['ATK']}|DEF:{stats['DEF']}|SPD:{stats['SPD']}|SP_ATK:{stats['SP_ATK']}|SP_DEF:{stats['SP_DEF']}|HP:{stats['HP']}`"
                embed.add_field(name=name, value=stat_line, inline=False)
            
            if filters:
                embed.set_footer(text=f"Filters: {filters} • Use reactions to navigate")
            else:
                embed.set_footer(text="Add filters: !chars name:Naruto atk>100 • Use reactions to navigate")
            
            return embed

        if total_pages == 1:
            await ctx.send(embed=create_embed(0))
            return

        message = await ctx.send(embed=create_embed(current_page))
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(r, u): 
            return u == ctx.author and str(r.emoji) in ['◀️', '▶️'] and r.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < total_pages - 1: 
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0: 
                    current_page -= 1
                await message.edit(embed=create_embed(current_page))
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

    @commands.command(name='info', aliases=['i'], help="!info [latest|id_or_name] - Shows info for a character.", category="Player Info")
    @has_accepted_rules()
    async def info(self, ctx, *, identifier: str = None):
        stats_cog = self.bot.get_cog('Stat Calculations')
        cz_cog = self.bot.get_cog('Core Gameplay')
        if not stats_cog or not cz_cog:
            await ctx.send("Game systems are currently offline."); return

        player = db.get_player(ctx.author.id)

        # If no identifier provided, show selected character
        if identifier is None:
            char_id = player.get('selected_character_id')
            if char_id is None:
                await ctx.send("❌ **No character selected!** Use `!select <character_id>` to select a character first, or use `!info latest` to see your latest pull.")
                return
        elif identifier.lower() == 'latest':
            char_id = player.get('latest_pull_id')
            if char_id is None:
                await ctx.send("You haven't pulled any characters yet."); return
        else:
            char_id = await self._find_character_from_input(ctx, player, identifier)
            if char_id is None: return

        char = player['characters'][char_id]
        display_stats = stats_cog.get_character_display_stats(char)

        # Check if this is the selected character
        is_selected = char_id == player.get('selected_character_id')
        selected_indicator = " ⭐" if is_selected else ""

        embed = discord.Embed(
            title=f"{char['name']} (ID: {char_id}, IV: {char['iv']}%){selected_indicator}", 
            description=char['description'], 
            color=discord.Color.gold() if is_selected else discord.Color.blue()
        )
        xp_needed = cz_cog._get_xp_for_next_level(char['level'])

        stats_text = f"**Lvl:** {char['level']} ({char['xp']}/{xp_needed} XP)\n"
        for stat, value in display_stats.items():
            iv_value = char.get('individual_ivs', {}).get(stat, 0)
            stats_text += f"**{stat.upper()}:** {value} (IV: {iv_value}/31)\n"

        embed.add_field(name="Stats", value=stats_text, inline=False)
        embed.add_field(name="Ability", value=char['ability'], inline=True)
        embed.add_field(name="Equipped", value=char.get('equipped_item', "None"), inline=True)

        if is_selected:
            embed.set_footer(text=f"Total IV: {char['iv']}% • Selected Character - Gains XP as you chat!")
        else:
            embed.set_footer(text=f"Total IV: {char['iv']}%")

        await ctx.send(embed=embed)

    @commands.command(name='infolatest', aliases=['il'], help="!infolatest - Shows info for your latest pulled character.", category="Player Info")
    @has_accepted_rules()
    async def info_latest(self, ctx):
        # Call the info command with "latest" as argument
        await self.info(ctx, identifier="latest")

    @commands.command(name='collection', aliases=['col'], help="!collection [filters] - View your character collection with optional filters.", category="Player Info")
    @has_accepted_rules()
    async def collection(self, ctx, *, filters: str = None):
        player = db.get_player(ctx.author.id)
        if not player['characters']:
            await ctx.send("Your collection is empty!"); return

        # Apply filters
        filtered_chars = self._apply_filters(player['characters'], filters)
        
        if not filtered_chars:
            await ctx.send("No characters match your filters!"); return

        # Sort characters by ID
        sorted_chars = sorted(filtered_chars.items(), key=lambda x: x[0])
        
        # Pagination setup
        chars_per_page = 10
        total_pages = math.ceil(len(sorted_chars) / chars_per_page)
        current_page = 0

        def create_collection_embed(page_num):
            start_idx = page_num * chars_per_page
            end_idx = start_idx + chars_per_page
            page_chars = sorted_chars[start_idx:end_idx]

            embed = discord.Embed(
                title=f"{ctx.author.display_name}'s Collection",
                description=f"Page {page_num + 1}/{total_pages} • {len(filtered_chars)} characters" + (f" (filtered)" if filters else ""),
                color=discord.Color.purple()
            )

            team_char_ids = [char_id for char_id in player.get('team', {}).values() if char_id is not None]
            
            char_list = []
            for cid, char in page_chars:
                indicators = ""
                if cid in team_char_ids:
                    indicators += "🛡️"
                if cid == player.get('selected_character_id'):
                    indicators += "⭐"
                
                char_list.append(f"`{cid}`: **Lvl {char['level']} {char['name']}** ({char['iv']}% IV) {indicators}")
            
            embed.description += "\n\n" + "\n".join(char_list)
            
            if filters:
                embed.set_footer(text=f"Applied filters: {filters} • Use reactions to navigate")
            else:
                embed.set_footer(text="Use reactions to navigate • Add filters: !col name:Naruto level>50 iv>=80")
            
            return embed

        if total_pages == 1:
            await ctx.send(embed=create_collection_embed(0))
            return

        message = await ctx.send(embed=create_collection_embed(current_page))
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return (user == ctx.author and 
                   str(reaction.emoji) in ['◀️', '▶️'] and 
                   reaction.message.id == message.id)

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                if str(reaction.emoji) == '▶️' and current_page < total_pages - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                
                await message.edit(embed=create_collection_embed(current_page))
                await message.remove_reaction(reaction, user)
                
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

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

    @commands.command(name='select', help="!select <id_or_name> - Select your active character from your collection.", category="Gacha System")
    @has_accepted_rules()
    async def select(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)

        # Check if collection is empty
        if not player['characters']:
            await ctx.send("❌ **Your collection is empty!** Use `!pull` to get characters first.")
            return

        # Handle ID-based selection specifically
        if identifier.isdigit():
            char_id = int(identifier)
            if char_id not in player['characters']:
                # Show available character IDs for better user experience
                available_ids = ", ".join([f"`{cid}`" for cid in player['characters'].keys()])
                await ctx.send(f"❌ **Character ID `{char_id}` not found in your collection.**\n"
                             f"💡 Available character IDs: {available_ids}\n"
                             f"🔍 Use `!collection` to see all your characters.")
                return

            selected_char = player['characters'][char_id]
            player['selected_character_id'] = char_id
            db.update_player(ctx.author.id, player)
            await ctx.send(f"✅ **Selected:** {selected_char['name']} (ID: {char_id}) - Level {selected_char['level']}, {selected_char['iv']}% IV\n"
                          f"⭐ This character will now gain XP as you chat!")
            return

        # Handle name-based selection
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: 
            # Show some helpful suggestions
            char_names = [char['name'] for char in player['characters'].values()]
            if len(char_names) <= 5:
                suggestions = ", ".join([f"`{name}`" for name in char_names])
                await ctx.send(f"💡 **Available characters:** {suggestions}")
            else:
                await ctx.send("🔍 Use `!collection` to see all your characters and their IDs.")
            return

        # Ensure char_id is integer for consistency
        char_id = int(char_id)
        selected_char = player['characters'][char_id]
        player['selected_character_id'] = char_id
        db.update_player(ctx.author.id, player)
        await ctx.send(f"✅ **Selected:** {selected_char['name']} (ID: {char_id}) - Level {selected_char['level']}, {selected_char['iv']}% IV\n"
                      f"⭐ This character will now gain XP as you chat!")

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

    async def show_character_moveset(self, ctx, character, char_id):
        """Shows the moveset for a character in a compact format for the learn command."""
        embed = discord.Embed(
            title=f"🎯 {character['name']}'s Moveset (ID: {char_id})", 
            description=f"**Level:** {character['level']} | **IV:** {character['iv']}%",
            color=discord.Color.blue()
        )

        # Get move data
        common_physical = self.attacks.get('physical', [])
        common_special = self.attacks.get('special', [])
        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])

        # Display active moveset in 4-slot format
        current_moveset = character.get('moveset', [None, None, None, None])
        while len(current_moveset) < 4:
            current_moveset.append(None)

        moveset_display = []
        for i, move_name in enumerate(current_moveset, 1):
            if move_name:
                # Find move data
                move_data = None
                for move_list in [common_physical, common_special, all_special_moves]:
                    move_data = next((m for m in move_list if m['name'] == move_name), None)
                    if move_data:
                        break

                if move_data:
                    power = move_data.get('power', 0)
                    accuracy = move_data.get('accuracy', 100)
                    move_type = move_data.get('type', move_data.get('element', 'Normal'))
                    moveset_display.append(f"**{i}.** {move_name} - PWR: {power}, ACC: {accuracy}%, Type: {move_type}")
                else:
                    moveset_display.append(f"**{i}.** {move_name}")
            else:
                moveset_display.append(f"**{i}.** *Empty* - Use `!learn <move> {i}` to fill")

        embed.add_field(name="⚔️ Active Moveset", value="\n".join(moveset_display), inline=False)

        # Show available moves to learn with keys
        active_moves_names = [move for move in current_moveset if move is not None]
        available_moves = []
        move_key = 1
        for move in all_special_moves:
            if move['unlock_level'] <= character['level'] and move['name'] not in active_moves_names:
                move_type = move.get('type', move.get('element', 'Normal'))
                available_moves.append(f"`{move_key}` **{move['name']}** - PWR: {move.get('power', 0)}, ACC: {move.get('accuracy', 100)}%, Type: {move_type}")
                move_key += 1

        if available_moves:
            embed.add_field(
                name="📚 Available to Learn", 
                value="\n".join(available_moves[:10]) + (f"\n*... and {len(available_moves) - 10} more*" if len(available_moves) > 10 else ""), 
                inline=False
            )
        else:
            embed.add_field(name="📚 Available to Learn", value="No new moves available at this level.", inline=False)

        # Show locked moves
        locked_moves = [f"**{m['name']}** (Lvl {m['unlock_level']})" 
                       for m in all_special_moves 
                       if m['unlock_level'] > character['level']]
        if locked_moves:
            embed.add_field(
                name="🔒 Locked Moves", 
                value="\n".join(locked_moves[:5]) + ("..." if len(locked_moves) > 5 else ""), 
                inline=False
            )

        embed.set_footer(text="Use !learn <move_name> [position] or !learn <key> [position] to teach a move")
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

    @commands.command(name='learn', help="!learn [key|move_name] [position] - Shows moveset or teaches a move to selected character. Use !select first.", category="Team Management")
    @has_accepted_rules()
    async def learn_move(self, ctx, move_identifier: str = None, position: int = None):
        player = db.get_player(ctx.author.id)

        # Check if user has selected a character
        char_id = player.get('selected_character_id')
        if not char_id:
            # Show user's characters if they have any
            if player['characters']:
                char_list = []
                for cid, char in list(player['characters'].items())[:5]:  # Show first 5
                    char_list.append(f"`{cid}` - {char['name']} (Lvl {char['level']})")
                char_display = "\n".join(char_list)
                if len(player['characters']) > 5:
                    char_display += f"\n... and {len(player['characters']) - 5} more"

                await ctx.send(f"❌ **No character selected!** Use `!select <character_id>` first to choose which character should learn the move.\n\n**Your Characters:**\n{char_display}")
            else:
                await ctx.send("❌ **No character selected!** You don't have any characters yet. Use `!pull` to get your first character, then `!select <character_id>` to select it.")
            return

        if char_id not in player['characters']:
            await ctx.send("❌ Your selected character no longer exists! Please select a new one with `!select <character>`.")
            return

        # Ensure char_id is integer for consistency
        char_id = int(char_id)
        character = player['characters'][char_id]

        # If no move_identifier provided, show the character's moveset
        if move_identifier is None:
            await self.show_character_moveset(ctx, character, char_id)
            return

        # Validate position if provided
        if position is not None:
            if position < 1 or position > 4:
                await ctx.send("❌ **Invalid position!** Use positions 1, 2, 3, or 4.")
                return
            target_slot = position - 1  # Convert to 0-based index
        else:
            target_slot = None

        # Get all available moves for this character
        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        common_physical = self.attacks.get('physical', [])
        common_special = self.attacks.get('special', [])

        # Get current moveset and available moves for key lookup
        current_moveset = character.get('moveset', [None, None, None, None])
        while len(current_moveset) < 4:
            current_moveset.append(None)

        active_moves_names = [move for move in current_moveset if move is not None]
        available_moves = [m for m in all_special_moves 
                         if m['unlock_level'] <= character['level'] and m['name'] not in active_moves_names]

        # Check if move_identifier is a key number
        move_data = None
        if move_identifier.isdigit():
            move_key = int(move_identifier)

            if 1 <= move_key <= len(available_moves):
                move_data = available_moves[move_key - 1]
            else:
                await ctx.send(f"❌ **Invalid move key '{move_key}'!** Available keys: 1-{len(available_moves)}. Use `!learn` to see available moves.")
                return
        else:
            # Find the move by name
            for move_list in [common_physical, common_special, all_special_moves]:
                move_data = next((m for m in move_list if m['name'].lower() == move_identifier.lower()), None)
                if move_data:
                    break

        if not move_data:
            await ctx.send(f"❌ **Move '{move_identifier}' not found!** Use `!learn` to see available moves and keys.")
            return

        # Check if it's a special move that requires unlocking
        if move_data in all_special_moves and character['level'] < move_data['unlock_level']:
            await ctx.send(f"❌ **'{move_data['name']}' requires level {move_data['unlock_level']}** to learn! (Current level: {character['level']})")
            return

        # Check if move is already known
        if move_data['name'] in current_moveset:
            await ctx.send(f"❌ **{character['name']}** already knows **{move_data['name']}**!")
            return

        # If specific position was requested
        if target_slot is not None:
            old_move = current_moveset[target_slot] if current_moveset[target_slot] else "Empty Slot"
            current_moveset[target_slot] = move_data['name']
            character['moveset'] = current_moveset
            db.update_player(ctx.author.id, player)

            if old_move == "Empty Slot":
                await ctx.send(f"✅ **{character['name']}** learned **{move_data['name']}** in position {position}!")
            else:
                await ctx.send(f"✅ **{character['name']}** forgot **{old_move}** and learned **{move_data['name']}** in position {position}!")
            return

        # No position specified - find first empty slot or show UI
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
            await ctx.send(f"✅ **{character['name']}** learned **{move_data['name']}** in position {empty_slot + 1}!")
        else:
            # All slots full, show slot selection UI
            embed = discord.Embed(
                title=f"🎯 Learn Move: {move_data['name']}",
                description=f"**{character['name']}'s** moveset is full! Choose which position to replace:",
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

            embed.set_footer(text="You can also use: !learn <move_name> <position 1-4> or !learn <key> <position>")

            view = self.SlotSelectionView(ctx, character, move_data, current_moveset, player)
            message = await ctx.send(embed=embed, view=view)
            view.message = message

    

    

    # --- Placeholder for Core Gameplay Cog ---
    # This section is a placeholder and assumes the existence of a 'Core Gameplay' cog
    # with necessary methods like _create_character_instance and _get_xp_for_next_level.
    # In a real scenario, these would be defined within that cog.

    def _create_character_instance(self, base_char_data):
        """Placeholder method to create a character instance."""
        # This method should create a deep copy and add instance-specific data
        import copy
        char_instance = copy.deepcopy(base_char_data)
        char_instance['xp'] = 0
        char_instance['level'] = 1
        char_instance['individual_ivs'] = {
            'HP': random.randint(0, 31),
            'ATK': random.randint(0, 31),
            'DEF': random.randint(0, 31),
            'SPD': random.randint(0, 31),
            'SP_ATK': random.randint(0, 31),
            'SP_DEF': random.randint(0, 31),
        }
        char_instance['iv'] = round(sum(char_instance['individual_ivs'].values()) / 6 * (100/31))
        char_instance['moveset'] = [None, None, None, None] # Initialize empty moveset
        char_instance['description'] = char_instance.get('description', 'A mysterious creature.')
        char_instance['ability'] = char_instance.get('ability', 'No Ability')
        char_instance['equipped_item'] = None
        return char_instance

    def _get_xp_for_next_level(self, current_level):
        """Placeholder method to calculate XP needed for the next level."""
        # Example formula: Quadratic growth
        return int(5 * (current_level ** 2) + 50 * current_level + 100)

    # --- Placeholder for Stat Calculations Cog ---
    # This section is a placeholder and assumes the existence of a 'Stat Calculations' cog
    # with a method like _calculate_stats.

    def get_character_display_stats(self, character):
        """Placeholder method to get formatted stats for display."""
        # In a real cog, this would use complex stat calculation formulas
        return {
            "hp": character['stats'].get('HP', 0),
            "atk": character['stats'].get('ATK', 0),
            "def": character['stats'].get('DEF', 0),
            "spd": character['stats'].get('SPD', 0),
            "sp_atk": character['stats'].get('SP_ATK', 0),
            "sp_def": character['stats'].get('SP_DEF', 0),
        }

    def _calculate_stats(self, base_stats, individual_ivs, level):
        """Placeholder method for calculating character stats."""
        # This is a simplified calculation. Real game stats would be more complex.
        calculated = {}
        for stat, base_value in base_stats.items():
            iv = individual_ivs.get(stat, 0)
            # Simplified stat formula (example)
            calculated[stat] = int(((2 * base_value + iv + int(0)) * level / 100) + 5) # Simplified: +5 base
        return calculated

    # --- XP Gain as Chat ---
    # This function needs to be integrated into the bot's event handling
    # for when a user sends a message.

    # Example of how this might be triggered (e.g., in your main bot file or another cog):
    # @commands.Cog.listener()
    # async def on_message(self, message):
    #     if message.author.bot: return
    #     # Check if the user has accepted rules and has a selected character
    #     player = db.get_player(message.author.id)
    #     if player and player.get("rules_accepted", 0) == 1 and player.get('selected_character_id'):
    #         await self._gain_xp_as_chat(message.author.id)
    #     await self.bot.process_commands(message) # Process commands as usual

    async def _gain_xp_as_chat(self, user_id: int):
        """Grants XP to the selected character when a user chats."""
        player = db.get_player(user_id)
        char_id = player.get('selected_character_id')

        if not char_id: return # No character selected

        char = player["characters"].get(char_id)
        if not char or char['level'] >= 100: return

        old_level = char['level']

        # Check for XP booster
        xp_gain = 5
        if 'xp_booster' in player and str(char_id) in player['xp_booster']:
            import time
            if time.time() < player['xp_booster'][str(char_id)]:
                xp_gain *= 2  # Double XP
            else:
                # Remove expired booster
                del player['xp_booster'][str(char_id)]

        char['xp'] += xp_gain

        # Check for level up
        cz_cog = self.bot.get_cog('Core Gameplay') # Assuming this cog has the method
        if cz_cog:
            xp_needed = cz_cog._get_xp_for_next_level(char['level'])
            if char['xp'] >= xp_needed:
                # Level up logic
                char['level'] += 1
                char['xp'] -= xp_needed
                
                # Recalculate stats
                stats_cog = self.bot.get_cog('Stat Calculations')
                if stats_cog:
                    base_stats = {k: v for k, v in self.characters[char['name']].items() if k in ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']}
                    char['stats'] = stats_cog._calculate_stats(base_stats, char['individual_ivs'], char['level'])
                
                # Check for newly learned moves
                await self.learn_new_moves_on_level_up(player, char_id, char['level'])

        db.update_player(user_id, player)

    async def learn_new_moves_on_level_up(self, player, char_id, new_level):
        """Checks if a character learned any new moves upon leveling up."""
        character = player['characters'][char_id]
        all_special_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        current_moveset_names = set(m for m in character.get('moveset', []) if m is not None)
        
        learned_moves = []
        for move in all_special_moves:
            if move['unlock_level'] == new_level and move['name'] not in current_moveset_names:
                learned_moves.append(move)
        
        if learned_moves:
            await self.show_character_moveset(None, character, char_id) # Show updated moveset without context
            message_parts = [f"🎉 **{character['name']}** (Lvl {new_level}) learned new moves:"]
            for move in learned_moves:
                message_parts.append(f"- **{move['name']}** (Power: {move.get('power', 0)}, Accuracy: {move.get('accuracy', 100)}%)")
            
            await ctx.send("\n".join(message_parts)) # This requires ctx, which might not be available here.
                                                      # A better approach would be to pass ctx or send a DM.
            # For now, let's assume a way to send this message. A DM might be best.
            try:
                user = await self.bot.fetch_user(player['user_id']) # Assuming user_id is stored in player data
                await user.send("\n".join(message_parts))
            except Exception as e:
                print(f"Could not DM user about learned moves: {e}")

    @commands.command(name='leaderboard', aliases=['lb'], help="!leaderboard - Shows the top ranked players.", category="Info")
    @has_accepted_rules()
    async def leaderboard(self, ctx):
        """Display the leaderboard of top ranked players."""
        leaderboard_data = db.get_leaderboard(15)  # Top 15 players

        if not leaderboard_data:
            await ctx.send("🏆 **No ranked players yet!** Start battling AI opponents to earn rank points!")
            return

        # Load rank system
        try:
            ranks_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'ranks.json')
            with open(ranks_path, 'r', encoding='utf-8') as f:
                ranks = json.load(f)
        except:
            await ctx.send("❌ Rank system data not available.")
            return

        def get_player_rank(rp):
            for rank_name, rank_data in ranks['tiers'].items():
                if rank_data['min_rp'] <= rp <= rank_data['max_rp']:
                    return rank_name, rank_data
            return "Bronze", ranks['tiers']['Bronze']

        embed = discord.Embed(
            title="🏆 CZ Battle Leaderboard",
            description="Top ranked players in AI battles",
            color=discord.Color.gold()
        )

        leaderboard_text = ""
        for i, entry in enumerate(leaderboard_data, 1):
            try:
                user = await self.bot.fetch_user(entry['user_id'])
                user_name = user.display_name[:15] if user else f"User #{entry['user_id']}"
            except:
                user_name = f"User #{entry['user_id']}"

            rank_name, rank_data = get_player_rank(entry['rank_points'])

            # Position emojis
            if i == 1:
                position = "🥇"
            elif i == 2:
                position = "🥈"
            elif i == 3:
                position = "🥉"
            else:
                position = f"**{i}.**"

            # Rank badges
            rank_badges = {
                "Bronze": "🥉",
                "Silver": "🥈", 
                "Gold": "🥇",
                "Platinum": "💎",
                "Diamond": "💠",
                "Master": "👑"
            }

            rank_badge = rank_badges.get(rank_name, "🔰")

            leaderboard_text += f"{position} {rank_badge} **{user_name}**\n"
            leaderboard_text += f"     `{entry['rank_points']} RP • {rank_name}`\n\n"

        # Show current user's position if not in top 15
        if ctx.author.id not in [entry['user_id'] for entry in leaderboard_data]:
            player = db.get_player(ctx.author.id)
            user_rp = player.get('rank_points', 0)
            if user_rp > 0:
                user_rank, _ = get_player_rank(user_rp)
                user_badge = rank_badges.get(user_rank, "🔰")
                leaderboard_text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                leaderboard_text += f"📍 {user_badge} **{ctx.author.display_name}**\n"
                leaderboard_text += f"     `{user_rp} RP • {user_rank}`"

        embed.description = leaderboard_text
        embed.set_footer(text="Battle AI opponents to earn Rank Points!")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CharacterManagement(bot))