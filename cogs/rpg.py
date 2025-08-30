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

        cog = ctx.bot.get_cog('CZ')
        if not cog or ctx.author.id in cog.rules_prompts.values():
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
        
        cog.rules_prompts[prompt_message.id] = ctx.author.id
        
        await ctx.send("Please accept the rules above to continue.", delete_after=10)
        return False

    return commands.check(predicate)

class CZ(commands.Cog):
    """A cog for the anime RPG game, now using a database."""
    def __init__(self, bot):
        self.bot = bot
        self.characters = load_json_data('characters.json')
        self.items = load_json_data('items.json')
        self.abilities = load_json_data('abilities.json')
        self.attacks = load_json_data('attacks.json')
        self.active_battles = set()
        self.rules_prompts = {}
        db.init_db()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or reaction.message.id not in self.rules_prompts or self.rules_prompts[reaction.message.id] != user.id:
            return
        
        if str(reaction.emoji) == '✅':
            player = db.get_player(user.id)
            player['rules_accepted'] = 1
            db.update_player(user.id, player)
            
            del self.rules_prompts[reaction.message.id]
            await reaction.message.delete()
            
            await user.send("✅ Thank you for accepting the rules! You can now use all CZ game commands.")

    def _get_xp_for_next_level(self, level):
        return (level ** 2) * 100

    def _get_unlocked_attacks(self, character, current_level):
        """Returns a list of attacks unlocked up to the current level."""
        char_id_str = str(character.get('id'))
        all_char_moves = self.attacks.get('characters', {}).get(char_id_str, [])
        unlocked_moves = [move for move in all_char_moves if move.get('unlock_level', 1) <= current_level]
        return unlocked_moves

    def _create_character_instance(self, base_character, iv):
        stats_dict = {k: v for k, v in base_character.items() if k not in ["Ability", "Description", "name", "id"]}
        if not stats_dict: return {}
        
        # Generate individual IVs for each stat (0-31)
        individual_ivs = {}
        total_iv_points = 0
        max_possible_iv_points = 31 * len(stats_dict)
        
        for stat in stats_dict.keys():
            # Generate a random IV between 0 and 31 for each stat
            individual_ivs[stat] = random.randint(0, 31)
            total_iv_points += individual_ivs[stat]
        
        # Calculate overall IV percentage
        iv_percentage = round((total_iv_points / max_possible_iv_points) * 100, 2)
        
        # Calculate actual stats based on base stats and individual IVs
        instance_stats = {}
        for stat, base_value in stats_dict.items():
            # Formula: final_stat = base_stat + (base_stat * (iv_value/31) * 0.3)
            iv_boost = base_value * (individual_ivs[stat]/31) * 0.3
            instance_stats[stat] = max(1, round(base_value + iv_boost))

        # Initial moveset for a new character (level 1)
        common_moves = [move['name'] for move in self.attacks.get('physical', [])[:1]] + [move['name'] for move in self.attacks.get('special', [])[:1]]
        char_id_str = str(base_character.get('id'))
        first_special = next((move['name'] for move in self.attacks.get('characters', {}).get(char_id_str, []) if move.get('unlock_level', 1) <= 1), None)
        
        initial_moveset = common_moves
        if first_special:
            initial_moveset.append(first_special)
        
        return {
            "id": base_character.get('id'), "name": base_character['name'], "iv": iv_percentage, "stats": instance_stats,
            "ability": base_character['Ability'], "description": base_character['Description'],
            "equipped_item": None, "level": 1, "xp": 0, "moveset": initial_moveset,
            "individual_ivs": individual_ivs
        }
        
    def _scale_character_to_level(self, base_char, level):
        # Create character with high IVs (for NPCs/enemies)
        instance = self._create_character_instance(base_char, 0)
        
        # Manually set high individual IVs (24-31 range for each stat)
        for stat in instance['individual_ivs'].keys():
            instance['individual_ivs'][stat] = random.randint(24, 31)
        
        # Recalculate overall IV percentage
        total_iv_points = sum(instance['individual_ivs'].values())
        max_possible_iv_points = 31 * len(instance['individual_ivs'])
        instance['iv'] = round((total_iv_points / max_possible_iv_points) * 100, 2)
        
        # Recalculate stats based on new IVs
        stats_dict = {k: v for k, v in base_char.items() if k not in ["Ability", "Description", "name", "id"]}
        for stat, base_value in stats_dict.items():
            iv_boost = base_value * (instance['individual_ivs'][stat]/31) * 0.3
            instance['stats'][stat] = max(1, round(base_value + iv_boost))
        
        # Add level-up stat bonuses
        stat_points_to_add = (level - 1) * 3
        stat_keys = list(instance['stats'].keys())
        for _ in range(stat_points_to_add):
            instance['stats'][random.choice(stat_keys)] += 1
        instance['level'] = level
        return instance

    def get_character_attacks(self, character):
        unlocked_attacks = []
        active_moves = character.get('moveset', [])
        all_possible_moves = self.attacks.get('physical', []) + self.attacks.get('special', []) + self.attacks.get('characters', {}).get(str(character.get('id')), [])
        
        for move_name in active_moves:
            move_data = next((m for m in all_possible_moves if m['name'] == move_name), None)
            if move_data:
                unlocked_attacks.append(move_data)
        return unlocked_attacks

    class CharacterSelectView(discord.ui.View):
        def __init__(self, author, available_characters):
            super().__init__(timeout=60.0)
            self.author = author
            self.available_characters = [c for c in available_characters if c['current_hp'] > 0]
            self.selected_character = None

            for character in self.available_characters:
                button = discord.ui.Button(
                    label=f"{character['name']} (HP: {character['current_hp']}/{character['stats']['HP']})", 
                    style=discord.ButtonStyle.success
                )
                async def button_callback(interaction: discord.Interaction, char=character):
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                        return
                    self.selected_character = char
                    self.stop()
                    await interaction.response.defer()
                button.callback = button_callback
                self.add_item(button)
        
        async def on_timeout(self):
            if self.available_characters:
                self.selected_character = self.available_characters[0]
            self.stop()
    
    class BattleView(discord.ui.View):
        def __init__(self, author, available_attacks):
            super().__init__(timeout=60.0)
            self.author = author
            self.available_attacks = available_attacks
            self.chosen_attack = None

            for attack in self.available_attacks:
                button = discord.ui.Button(label=attack['name'], style=discord.ButtonStyle.primary)
                async def button_callback(interaction: discord.Interaction, atk=attack):
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("This isn't your turn!", ephemeral=True)
                        return
                    self.chosen_attack = atk
                    self.stop()
                    await interaction.response.defer()
                button.callback = button_callback
                self.add_item(button)
        
        async def on_timeout(self):
            if self.available_attacks:
                self.chosen_attack = self.available_attacks[0]
            self.stop()
            
    class CharacterSelectView(discord.ui.View):
        def __init__(self, author, team):
            super().__init__(timeout=60.0)
            self.author = author
            self.team = team
            self.selected_character = None

            for character in self.team:
                if character['current_hp'] <= 0:
                    continue  # Skip defeated characters
                button = discord.ui.Button(
                    label=f"{character['name']} (HP: {character['current_hp']}/{character['stats']['HP']})", 
                    style=discord.ButtonStyle.secondary
                )
                async def button_callback(interaction: discord.Interaction, char=character):
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                        return
                    self.selected_character = char
                    self.stop()
                    await interaction.response.defer()
                button.callback = button_callback
                self.add_item(button)
        
        async def on_timeout(self):
            # Auto-select the first available character if timeout
            for char in self.team:
                if char['current_hp'] > 0:
                    self.selected_character = char
                    break
            self.stop()

    @commands.command(name='pull', aliases=['p'], help="!pull - Spend 50 coins to get a random character.", category="Economic")
    @has_accepted_rules()
    async def pull(self, ctx):
        player = db.get_player(ctx.author.id)
        if player['coins'] < 50:
            await ctx.send("You don't have enough coins! (Need 50)"); return
        if not self.characters:
            await ctx.send("Character data is not loaded."); return

        player['coins'] -= 50
        char_name, char_data = random.choice(list(self.characters.items()))
        base_char = {"name": char_name, **char_data}
        
        # Create character instance with the new IV system
        new_char_instance = self._create_character_instance(base_char, 0)
        char_id = player['next_character_id']
        player['characters'][char_id] = new_char_instance
        player['latest_pull_id'] = char_id
        player['next_character_id'] += 1
        
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You pulled **{char_name}** with **{new_char_instance['iv']}% IV**! Use `!info latest` to see their stats.")

    @commands.command(name='balance', aliases=['bal'], help="!balance - Check your coin balance.", category="Economic")
    @has_accepted_rules()
    async def balance(self, ctx):
        player = db.get_player(ctx.author.id)
        await ctx.send(f"💰 You have **{player['coins']}** coins.")

    @commands.command(name='daily', help="!daily - Claim your daily coins.", category="Economic")
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

    @commands.command(name='allcharacters', aliases=['chars', 'characters'], help="!characters [sort_key] - View all characters.", category="Fun")
    @has_accepted_rules()
    async def allcharacters(self, ctx, sort_by: str = "name"):
        valid_sorts = ['atk', 'def', 'spd', 'res', 'hp', 'name']
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
                embed.add_field(name=name, value=f"`ATK:{stats['ATK']}|DEF:{stats['DEF']}|SPD:{stats['SPD']}|RES:{stats['RES']}|HP:{stats['HP']}`", inline=False)
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

    @commands.command(name='info', aliases=['il'], help="!info [latest|id] - Shows info for a character.", category="Fun")
    @has_accepted_rules()
    async def info(self, ctx, char_identifier: str = "latest"):
        player = db.get_player(ctx.author.id)
        char_id = player['latest_pull_id'] if char_identifier.lower() == 'latest' else int(char_identifier) if char_identifier.isdigit() else None
        
        if char_id is None:
            await ctx.send("Invalid input. Use `!info latest` or `!info <character_id>`."); return
        if char_id not in player['characters']:
            await ctx.send("You don't own a character with that ID."); return
            
        char = player['characters'][char_id]
        embed = discord.Embed(title=f"{char['name']} (ID: {char_id}, IV: {char['iv']}%)", description=char['description'], color=discord.Color.blue())
        xp_needed = self._get_xp_for_next_level(char['level'])
        
        # Display stats with individual IVs
        stats_text = f"**Lvl:** {char['level']} ({char['xp']}/{xp_needed} XP)\n"
        
        # Add each stat with its IV value
        for stat, value in char['stats'].items():
            iv_value = char.get('individual_ivs', {}).get(stat, 0)
            stats_text += f"**{stat}:** {value} - IV: {iv_value}/31\n"
        
        embed.add_field(name="Stats", value=stats_text, inline=False)
        embed.add_field(name="Ability", value=char['ability'], inline=True)
        embed.add_field(name="Equipped", value=char.get('equipped_item', "None"), inline=True)
        
        # New move display logic
        all_possible_moves = self.attacks.get('characters', {}).get(str(char['id']), [])
        
        moveset_names = [m['name'] for m in all_possible_moves if m['name'] in char['moveset']]
        unlocked_names = [m['name'] for m in all_possible_moves if m['name'] not in moveset_names and m['unlock_level'] <= char['level']]
        locked_moves = [m for m in all_possible_moves if m['unlock_level'] > char['level']]
        
        active_moves = "\n".join(f"`{name}`" for name in moveset_names) or "No moves equipped."
        available_moves = "\n".join(f"`{name}`" for name in unlocked_names) or "No other moves unlocked."
        upcoming_moves = "\n".join(f"`{m['name']}` (Lvl {m['unlock_level']})" for m in locked_moves) or "No upcoming moves."
        
        embed.add_field(name="⚔️ Active Moveset", value=active_moves, inline=False)
        embed.add_field(name="📚 Available Moves", value=available_moves, inline=True)
        embed.add_field(name="🔒 Locked Moves", value=upcoming_moves, inline=True)
        embed.set_footer(text=f"Total Stats: {sum(char['stats'].values())} | Total IV: {char['iv']}%")
        await ctx.send(embed=embed)
            
    @commands.command(name='collection', aliases=['col'], help="!collection - View your character collection.", category="Fun")
    @has_accepted_rules()
    async def collection(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['characters']:
            await ctx.send("Your collection is empty!"); return
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Collection", color=discord.Color.purple())
        desc = "".join([f"`{cid}`: **Lvl {c['level']} {c['name']}** ({c['iv']}% IV) {'🛡️' if cid in player['team'] else ''}{'⭐' if cid == player['selected_character_id'] else ''}\n" for cid, c in player['characters'].items()])
        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(name='select', help="!select <id> - Select your active character for XP gain.", category="Team")
    @has_accepted_rules()
    async def select(self, ctx, char_id: int):
        player = db.get_player(ctx.author.id)
        if char_id not in player['characters']:
            await ctx.send("You don't own a character with that ID."); return
        player['selected_character_id'] = char_id
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You have selected **{player['characters'][char_id]['name']}** to gain XP.")

    @commands.group(name='shop', invoke_without_command=True, help="!shop - Displays the item shop.", category="Shop")
    @has_accepted_rules()
    async def shop(self, ctx):
        embed = discord.Embed(title="Shop", description="Welcome!", color=discord.Color.gold())
        embed.add_field(name="Item Box", value="Costs 200 coins.\nUse `!shop buy itembox`", inline=False)
        await ctx.send(embed=embed)

    @shop.command(name='buy')
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
        player['inventory'][item_full_name] += 1
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You bought an Item Box and found a **{item_full_name}**!")
    
    @commands.command(name='inventory', aliases=['inv'], help="!inventory - View your items.", category="Fun")
    @has_accepted_rules()
    async def inventory(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['inventory']:
            await ctx.send("Your inventory is empty."); return
        embed = discord.Embed(title="Your Inventory", color=discord.Color.orange())
        embed.description = "\n".join(f"**{name}**: x{count}" for name, count in player['inventory'].items())
        await ctx.send(embed=embed)

    @commands.group(name='team', aliases=['t'], invoke_without_command=True, help="!team [view|create|remove]", category="Team")
    @has_accepted_rules()
    async def team(self, ctx):
        await self.view_team(ctx)

    @team.command(name='view', aliases=['v'])
    @has_accepted_rules()
    async def view_team(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['team']:
            await ctx.send("You don't have a team. Use `!team create <id1> ...`"); return
        embed = discord.Embed(title="Your Active Team", color=discord.Color.green())
        for char_id in player['team']:
            char_info = player['characters'][char_id]
            embed.add_field(name=f"{char_info['name']} (ID: {char_id})", value=f"Lvl {char_info['level']}, IV: {char_info['iv']}%", inline=False)
        await ctx.send(embed=embed)

    @team.command(name='create', aliases=['c'])
    @has_accepted_rules()
    async def create_team(self, ctx, *char_ids: int):
        player = db.get_player(ctx.author.id)
        if not 1 <= len(char_ids) <= 3:
            await ctx.send("Please provide 1 to 3 character IDs."); return
        if len(set(char_ids)) != len(char_ids):
            await ctx.send("You cannot have duplicate characters on a team."); return
            
        new_team = []
        for char_id in char_ids:
            if char_id not in player['characters']:
                await ctx.send(f"ID `{char_id}` not found in your collection."); return
            new_team.append(char_id)
        player['team'] = new_team
        db.update_player(ctx.author.id, player)
        await ctx.send("Team set!"); await self.view_team(ctx)

    @team.command(name='remove', aliases=['r'])
    @has_accepted_rules()
    async def remove_from_team(self, ctx, char_id: int):
        player = db.get_player(ctx.author.id)
        if char_id not in player['team']:
            await ctx.send("That character isn't in your team."); return
        player['team'].remove(char_id)
        db.update_player(ctx.author.id, player)
        await ctx.send("Character removed."); await self.view_team(ctx)

    @commands.command(name='equip', aliases=['eq'], help="!equip <char_id> <item name>", category="Team")
    @has_accepted_rules()
    async def equip(self, ctx, char_id: int, *, item_name: str):
        player = db.get_player(ctx.author.id)
        if char_id not in player['characters']:
            await ctx.send("Invalid character ID."); return
        
        item_name_lower = item_name.lower()
        found_item = next((inv_item for inv_item in player['inventory'] if item_name_lower == inv_item.lower()), None)
        if not found_item or player['inventory'][found_item] == 0:
            await ctx.send(f"You don't have an item named '{item_name}'."); return
            
        character = player['characters'][char_id]
        if character['equipped_item']:
            await ctx.send(f"Unequip the current item first with `!unequip {char_id}`."); return
        
        character['equipped_item'] = found_item
        player['inventory'][found_item] -= 1
        if player['inventory'][found_item] == 0: del player['inventory'][found_item]
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Equipped **{found_item}** on **{character['name']}**.")

    @commands.command(name='unequip', aliases=['ue'], help="!unequip <char_id>", category="Team")
    @has_accepted_rules()
    async def unequip(self, ctx, char_id: int):
        player = db.get_player(ctx.author.id)
        if char_id not in player['characters']:
            await ctx.send("Invalid character ID."); return
        
        character = player['characters'][char_id]
        item_name = character['equipped_item']
        if not item_name:
            await ctx.send(f"{character['name']} has no item equipped."); return
            
        character['equipped_item'] = None
        player['inventory'][item_name] += 1
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Unequipped **{item_name}** from **{character['name']}**.")

    @commands.group(name='moves', aliases=['m'], invoke_without_command=True, help="!moves [id] - View your character's moves.", category="Team")
    @has_accepted_rules()
    async def moves(self, ctx, char_id: int = None):
        player = db.get_player(ctx.author.id)
        if char_id is None:
            char_id = player.get('selected_character_id')
            if not char_id:
                await ctx.send("Please select a character first with `!select <id>` or specify an ID."); return
        
        if char_id not in player['characters']:
            await ctx.send("You don't own a character with that ID."); return
            
        character = player['characters'][char_id]
        embed = discord.Embed(title=f"Moveset for {character['name']} (Lvl {character['level']})", color=discord.Color.orange())
        
        all_possible_moves = self.attacks.get('characters', {}).get(str(character.get('id')), [])
        active_moves_names = character.get('moveset', [])
        
        active_moves_details = [f"**{m['name']}** - Power: {m.get('power', 0)}, Acc: {m.get('accuracy', 100)}%"
                                for m_name in active_moves_names
                                if (m := next((m for m in self.attacks.get('physical', []) + self.attacks.get('special', []) + all_possible_moves if m['name'] == m_name), None))]
        embed.add_field(name="⚔️ Active Moveset", value="\n".join(active_moves_details) or "None", inline=False)

        unlocked_and_inactive = [f"**{m['name']}** - Power: {m.get('power', 0)}, Acc: {m.get('accuracy', 100)}%"
                                for m in all_possible_moves
                                if m['unlock_level'] <= character['level'] and m['name'] not in active_moves_names]
        if unlocked_and_inactive:
            embed.add_field(name="📚 Unlocked (Inactive)", value="\n".join(unlocked_and_inactive), inline=False)
            
        locked_moves = [f"**{m['name']}** (Lvl {m['unlock_level']})"
                        for m in all_possible_moves
                        if m['unlock_level'] > character['level']]
        if locked_moves:
            embed.add_field(name="🔒 Locked", value="\n".join(locked_moves), inline=False)

        embed.set_footer(text="Use `!moves swap` to change your active moveset.")
        await ctx.send(embed=embed)

    @moves.command(name='swap')
    @has_accepted_rules()
    async def swap_moves(self, ctx, char_id: int, new_move: str, old_move: str):
        player = db.get_player(ctx.author.id)
        if char_id not in player['characters']:
            await ctx.send("You don't own a character with that ID."); return

        character = player['characters'][char_id]
        common_move_names = [m['name'].lower() for m in self.attacks.get('physical', []) + self.attacks.get('special', [])]
        old_move_name = next((m for m in character.get('moveset', []) if m.lower() == old_move.lower()), None)
        
        if not old_move_name:
            await ctx.send(f"'{old_move}' is not in your active moveset."); return

        # Prevent swapping out common attacks, as they are the default moves
        if old_move_name.lower() in [m['name'].lower() for m in self.attacks['physical']] or old_move_name.lower() in [m['name'].lower() for m in self.attacks['special']]:
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
    
    @commands.command(name='battle', help="!battle <member> | !battle @bot [level]", category="Battle")
    @has_accepted_rules()
    async def battle(self, ctx, opponent: discord.Member, level: int = None):
        challenger = ctx.author

        if opponent.id == self.bot.user.id:
            player_team_data = db.get_player(challenger.id)
            if not player_team_data['team']: await ctx.send("You need a team to battle!"); return
            if level is None:
                team_levels = [player_team_data['characters'][cid]['level'] for cid in player_team_data['team']]
                level = max(1, sum(team_levels) // len(team_levels))
            if not 1 <= level <= 100: await ctx.send("Level must be between 1 and 100."); return
            bot_team_chars = random.sample(list(self.characters.items()), 3)
            bot_team = [self._scale_character_to_level({"name": name, **data}, level) for name, data in bot_team_chars]
            await self._run_interactive_battle(ctx, challenger, self.bot.user, db.get_player(challenger.id), None, bot_team=bot_team)
            return

        if challenger == opponent: await ctx.send("You can't challenge yourself!"); return
        if opponent.bot: await ctx.send("You can't challenge a bot this way."); return
        
        battle_key = tuple(sorted((challenger.id, opponent.id)))
        if battle_key in self.active_battles: await ctx.send("One of you is already in a battle!"); return
        
        challenger_player, opponent_player = db.get_player(challenger.id), db.get_player(opponent.id)
        if not challenger_player['team']: await ctx.send("You need a team first."); return
        if not opponent_player['team']: await ctx.send(f"{opponent.display_name} does not have a team."); return
        
        req_msg = await ctx.send(f"{opponent.mention}, you've been challenged by {challenger.mention}! React with ✅ to accept.")
        await req_msg.add_reaction('✅'); await req_msg.add_reaction('❌')
        def check(r, u): return u == opponent and str(r.emoji) in ['✅', '❌'] and r.message.id == req_msg.id
        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == '❌': await req_msg.edit(content=f"{opponent.display_name} declined."); return
        except asyncio.TimeoutError: await req_msg.edit(content="Battle request timed out."); return
        await req_msg.delete()
        await self._run_interactive_battle(ctx, challenger, opponent, challenger_player, opponent_player)

    async def _run_interactive_battle(self, ctx, p1_user, p2_user, p1_data, p2_data, bot_team=None):
        battle_key = tuple(sorted((p1_user.id, p2_user.id)))
        self.active_battles.add(battle_key)

        def prep_team(player_data):
            team = []
            if not player_data: return []
            for char_id in player_data.get('team', []):
                inst = player_data['characters'][char_id].copy()
                inst['current_hp'] = inst['stats']['HP']
                inst['char_id'] = char_id  # Store the character ID for reference
                if inst['equipped_item']:
                    name, rarity = inst['equipped_item'].rsplit(' ', 1)
                    if name in self.items and rarity in self.items[name]:
                        boost = self.items[name][rarity]
                        stat, val = boost['stat'], int(inst['stats'][boost['stat']] * (boost['boost'] / 100))
                        inst['stats'][stat] += val
                team.append(inst)
            return team

        team1, team2 = prep_team(p1_data), bot_team if bot_team else prep_team(p2_data)
        log = []
        battle_message = None
        
        # Active character tracking
        active_char1 = None
        active_char2 = None
        pending_damage = None
        pending_target = None
        
        # Character selection at battle start
        if not p1_user.bot and team1:
            embed = discord.Embed(title=f"Battle Start: {p1_user.display_name} vs {p2_user.display_name}", 
                                 description="Select your starting character!", 
                                 color=discord.Color.blue())
            view = self.CharacterSelectView(p1_user, team1)
            battle_message = await ctx.send(embed=embed, view=view)
            await view.wait()
            active_char1 = view.selected_character
            if not active_char1 and team1:  # Fallback if no selection
                active_char1 = team1[0]
            log.append(f"🔄 {p1_user.display_name} selected {active_char1['name']} to start the battle!")
        elif team1:
            active_char1 = team1[0]  # Bot selects first character
            log.append(f"🔄 {p1_user.display_name} selected {active_char1['name']} to start the battle!")
            
        if not p2_user.bot and team2:
            embed = discord.Embed(title=f"Battle Start: {p1_user.display_name} vs {p2_user.display_name}", 
                                 description="Select your starting character!", 
                                 color=discord.Color.blue())
            view = self.CharacterSelectView(p2_user, team2)
            if battle_message:
                await battle_message.edit(embed=embed, view=view)
            else:
                battle_message = await ctx.send(embed=embed, view=view)
            await view.wait()
            active_char2 = view.selected_character
            if not active_char2 and team2:  # Fallback if no selection
                active_char2 = team2[0]
            log.append(f"🔄 {p2_user.display_name} selected {active_char2['name']} to start the battle!")
        elif team2:
            active_char2 = team2[0]  # Bot selects first character
            log.append(f"🔄 {p2_user.display_name} selected {active_char2['name']} to start the battle!")
        
        # Create turn order based on active characters' speed
        turn_order = [active_char1, active_char2]
        turn_order.sort(key=lambda x: x['stats']['SPD'], reverse=True)
        turn = 0
        
        # Main battle loop
        while any(c['current_hp'] > 0 for c in team1) and any(c['current_hp'] > 0 for c in team2):
            turn += 1
            attacker = turn_order[(turn - 1) % len(turn_order)]
            
            # Skip if attacker is defeated
            if attacker['current_hp'] <= 0:
                # Replace with next available character from the same team
                is_p1_char = attacker == active_char1
                available_chars = [c for c in (team1 if is_p1_char else team2) if c['current_hp'] > 0]
                if not available_chars:
                    continue  # No available characters, skip turn
                    
                if is_p1_char:
                    active_char1 = available_chars[0]
                    attacker = active_char1
                    turn_order[turn_order.index(attacker)] = active_char1
                    log.append(f"🔄 {p1_user.display_name}'s {active_char1['name']} enters the battle!")
                else:
                    active_char2 = available_chars[0]
                    attacker = active_char2
                    turn_order[turn_order.index(attacker)] = active_char2
                    log.append(f"🔄 {p2_user.display_name}'s {active_char2['name']} enters the battle!")
            
            is_p1_turn = attacker == active_char1
            current_player = p1_user if is_p1_turn else p2_user
            defender = active_char2 if is_p1_turn else active_char1
            current_team = team1 if is_p1_turn else team2
            opponent_team = team2 if is_p1_turn else team1
            
            # Check if there are any living defenders
            if defender['current_hp'] <= 0:
                available_defenders = [c for c in opponent_team if c['current_hp'] > 0]
                if not available_defenders:
                    break  # No available defenders, battle ends
                defender = available_defenders[0]
                if is_p1_turn:
                    active_char2 = defender
                else:
                    active_char1 = defender
                log.append(f"🔄 {defender['name']} enters the battle!")
            
            # Option to switch character or attack
            switch_option = False
            chosen_attack = None
            
            if not current_player.bot:
                # Create embed for turn
                embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, 
                                               f"It's {current_player.display_name}'s turn with {attacker['name']}!")
                
                # Add switch button
                available_chars = [c for c in current_team if c['current_hp'] > 0 and c != attacker]
                if available_chars:
                    switch_view = discord.ui.View(timeout=60.0)
                    switch_button = discord.ui.Button(label="Switch Character", style=discord.ButtonStyle.success)
                    attack_button = discord.ui.Button(label="Attack", style=discord.ButtonStyle.danger)
                    
                    async def switch_callback(interaction):
                        if interaction.user.id != current_player.id:
                            await interaction.response.send_message("This isn't your turn!", ephemeral=True)
                            return
                        nonlocal switch_option
                        switch_option = True
                        switch_view.stop()
                        await interaction.response.defer()
                        
                    async def attack_callback(interaction):
                        if interaction.user.id != current_player.id:
                            await interaction.response.send_message("This isn't your turn!", ephemeral=True)
                            return
                        switch_view.stop()
                        await interaction.response.defer()
                    
                    switch_button.callback = switch_callback
                    attack_button.callback = attack_callback
                    switch_view.add_item(switch_button)
                    switch_view.add_item(attack_button)
                    
                    if battle_message:
                        await battle_message.edit(embed=embed, view=switch_view)
                    else:
                        battle_message = await ctx.send(embed=embed, view=switch_view)
                    
                    await switch_view.wait()
                    
                    # Handle character switch
                    if switch_option:
                        char_select_view = self.CharacterSelectView(current_player, available_chars)
                        embed.description = f"Select a character to switch to:"
                        await battle_message.edit(embed=embed, view=char_select_view)
                        await char_select_view.wait()
                        
                        if char_select_view.selected_character:
                            new_char = char_select_view.selected_character
                            if is_p1_turn:
                                active_char1 = new_char
                                turn_order[turn_order.index(attacker)] = active_char1
                            else:
                                active_char2 = new_char
                                turn_order[turn_order.index(attacker)] = active_char2
                                
                            log.append(f"🔄 {current_player.display_name} switched to {new_char['name']}!")
                            
                            # Apply pending damage if there was an attack
                            if pending_damage and pending_target == (1 if is_p1_turn else 2):
                                new_char['current_hp'] = max(0, new_char['current_hp'] - pending_damage)
                                log.append(f"💥 The pending attack hits {new_char['name']} for **{pending_damage}** damage!")
                                if new_char['current_hp'] == 0:
                                    log.append(f"💀 {new_char['name']} has been defeated!")
                                pending_damage = None
                                pending_target = None
                            
                            # Update the battle display and continue to next turn
                            if len(log) > 5: log.pop(0)
                            final_turn_embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user)
                            await battle_message.edit(embed=final_turn_embed, view=None)
                            await asyncio.sleep(2)
                            continue
                
                # If not switching or after switch UI, show attack options
                available_attacks = self.get_character_attacks(attacker)
                attack_view = self.BattleView(current_player, available_attacks)
                embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, 
                                               f"Select an attack for {attacker['name']}!")
                await battle_message.edit(embed=embed, view=attack_view)
                await attack_view.wait()
                chosen_attack = attack_view.chosen_attack
            else:
                # Bot's turn logic
                available_attacks = self.get_character_attacks(attacker)
                chosen_attack = random.choice(available_attacks)
                
                # Bots have a chance to switch characters if they have low HP
                if attacker['current_hp'] < attacker['stats']['HP'] * 0.3:  # Below 30% HP
                    available_chars = [c for c in current_team if c['current_hp'] > 0 and c != attacker]
                    if available_chars and random.random() < 0.7:  # 70% chance to switch when low HP
                        new_char = random.choice(available_chars)
                        if is_p1_turn:
                            active_char1 = new_char
                            turn_order[turn_order.index(attacker)] = active_char1
                        else:
                            active_char2 = new_char
                            turn_order[turn_order.index(attacker)] = active_char2
                            
                        log.append(f"🔄 {current_player.display_name} switched to {new_char['name']}!")
                        
                        # Apply pending damage if there was an attack
                        if pending_damage and pending_target == (1 if is_p1_turn else 2):
                            new_char['current_hp'] = max(0, new_char['current_hp'] - pending_damage)
                            log.append(f"💥 The pending attack hits {new_char['name']} for **{pending_damage}** damage!")
                            if new_char['current_hp'] == 0:
                                log.append(f"💀 {new_char['name']} has been defeated!")
                            pending_damage = None
                            pending_target = None
                        
                        # Update the battle display and continue to next turn
                        if len(log) > 5: log.pop(0)
                        final_turn_embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user)
                        if battle_message:
                            await battle_message.edit(embed=final_turn_embed, view=None)
                        else:
                            battle_message = await ctx.send(embed=final_turn_embed)
                        await asyncio.sleep(2)
                        continue

            # Handle attack execution
            if not chosen_attack:  # Handle timeout case
                chosen_attack = self.attacks.get('physical', [None])[0] or self.attacks.get('special', [None])[0]
                if not chosen_attack:
                    await ctx.send("An attack could not be determined. Battle ending."); break

            # Update attacker reference in case it changed due to switching
            attacker = active_char1 if is_p1_turn else active_char2
            defender = active_char2 if is_p1_turn else active_char1
            
            log.append(f"▶️ {attacker['name']} uses **{chosen_attack['name']}**!")
            
            # Calculate damage with improved formula
            if random.randint(1, 100) > chosen_attack.get('accuracy', 100):
                log.append(f"💨 The attack missed!")
            else:
                # Enhanced damage calculation
                power = chosen_attack.get('power', 0)
                atk = attacker['stats']['ATK']
                sp_atk = attacker['stats'].get('SP_ATK', 0)
                defense = defender['stats']['DEF']
                res = defender['stats'].get('SP_DEF', 0)
                
                # Determine if attack is physical or special based on type attribute
                is_physical = chosen_attack.get('type') == 'physical'
                
                # Calculate base damage using appropriate attack stat
                if not is_physical and sp_atk > 0:
                    attack_stat = sp_atk
                    defense_stat = res
                else:
                    attack_stat = atk
                    defense_stat = defense
                
                # Critical hit chance (10%)
                critical = random.random() < 0.1
                crit_multiplier = 1.5 if critical else 1.0
                
                # Base damage formula with stat scaling
                # Using a simplified formula for better balance
                base_damage = (power * attack_stat) / (100 + defense_stat)
                
                # Apply critical hit and randomness factor (85-100%)
                random_factor = random.uniform(0.85, 1.0)
                damage = max(1, round(base_damage * crit_multiplier * random_factor))
                
                # Store damage for potential character switching
                pending_damage = damage
                pending_target = 2 if is_p1_turn else 1
                
                # Apply damage to current defender
                defender['current_hp'] = max(0, defender['current_hp'] - damage)
                
                # Create detailed damage message
                damage_msg = f"💥 It hits {defender['name']} for **{damage}** damage!"
                if critical:
                    damage_msg += " 🔥 Critical hit!"
                log.append(damage_msg)
                
                if defender['current_hp'] == 0:
                    log.append(f"💀 {defender['name']} has been defeated!")
                    
                    # Clear pending damage since it was applied
                    pending_damage = None
                    pending_target = None
            
            if len(log) > 5: log.pop(0)
            final_turn_embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user)
            if battle_message:
                await battle_message.edit(embed=final_turn_embed, view=None)
            else:
                battle_message = await ctx.send(embed=final_turn_embed)
            await asyncio.sleep(2)

        # Determine winner
        winner = p1_user if any(c['current_hp'] > 0 for c in team1) else p2_user
        loser = p2_user if winner == p1_user else p1_user
        
        # Create a more visually appealing final embed
        final_embed = discord.Embed(
            title=f"🏆 Battle Concluded! 🏆",
            description=f"**{winner.display_name}** has emerged victorious against **{loser.display_name}**!",
            color=discord.Color.gold()
        )
        
        # Show final team status with more details
        t1_status = []
        for c in team1:
            status = f"**{c['name']}**: {round(c['current_hp'])}/{c['stats']['HP']} HP"
            if c['current_hp'] <= 0:
                status += " (💀 Defeated)"
            else:
                status += f" (❤️ {round(c['current_hp']/c['stats']['HP']*100)}% remaining)"
            t1_status.append(status)
            
        t2_status = []
        for c in team2:
            status = f"**{c['name']}**: {round(c['current_hp'])}/{c['stats']['HP']} HP"
            if c['current_hp'] <= 0:
                status += " (💀 Defeated)"
            else:
                status += f" (❤️ {round(c['current_hp']/c['stats']['HP']*100)}% remaining)"
            t2_status.append(status)
            
        final_embed.add_field(name=f"{p1_user.display_name}'s Team", value="\n".join(t1_status) or "Defeated", inline=True)
        final_embed.add_field(name=f"{p2_user.display_name}'s Team", value="\n".join(t2_status) or "Defeated", inline=True)
        final_embed.add_field(name="Battle Log", value="\n".join(log) or "Battle ended!", inline=False)
        
        # Add a footer with battle statistics
        final_embed.set_footer(text=f"Battle concluded after {turn} turns | Character switching enabled | Enhanced damage system")
        
        await battle_message.edit(embed=final_embed, view=None)
        self.active_battles.remove(battle_key)

    def _create_battle_embed(self, log, t1, t2, p1_user, p2_user, footer_text=None):
        embed = discord.Embed(title=f"⚔️ {p1_user.display_name} vs {p2_user.display_name}", color=discord.Color.red())
        
        # Highlight active characters with emoji indicators
        t1_status = []
        for c in t1:
            status_line = f"**{c['name']}**: {round(c['current_hp'])}/{c['stats']['HP']} HP"
            # Add stat display for active characters
            if c['current_hp'] > 0:
                status_line += f" | ATK: {c['stats']['ATK']} | DEF: {c['stats']['DEF']}"
            # Add indicator for active character
            if any(c == active for active in ([t1[0]] if t1 else [])):
                status_line = f"▶️ {status_line}"
            t1_status.append(status_line)
            
        t2_status = []
        for c in t2:
            status_line = f"**{c['name']}**: {round(c['current_hp'])}/{c['stats']['HP']} HP"
            # Add stat display for active characters
            if c['current_hp'] > 0:
                status_line += f" | ATK: {c['stats']['ATK']} | DEF: {c['stats']['DEF']}"
            # Add indicator for active character
            if any(c == active for active in ([t2[0]] if t2 else [])):
                status_line = f"▶️ {status_line}"
            t2_status.append(status_line)
            
        embed.add_field(name=f"{p1_user.display_name}'s Team", value="\n".join(t1_status) or "Defeated", inline=True)
        embed.add_field(name=f"{p2_user.display_name}'s Team", value="\n".join(t2_status) or "Defeated", inline=True)
        embed.add_field(name="Battle Log", value="\n".join(log) or "Battle starts!", inline=False)
        if footer_text:
            embed.set_footer(text=footer_text)
        return embed

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or (await self.bot.get_context(message)).valid: return
        
        player = db.get_player(message.author.id)
        if not player.get("rules_accepted", 0): return

        char_id = player.get("selected_character_id")
        if not char_id or time.time() - player.get("last_xp_gain_time", 0) < 60: return
        
        player["last_xp_gain_time"] = time.time()
        char = player["characters"].get(char_id)
        if not char or char['level'] >= 100: return
        
        old_level = char['level']
        
        char['xp'] += random.randint(5, 15)
        xp_needed = self._get_xp_for_next_level(char['level'])
        
        leveled_up = False
        while char['xp'] >= xp_needed:
            if char['level'] >= 100: char['xp'] = 0; break
            char['level'] += 1; char['xp'] -= xp_needed
            leveled_up = True
            for _ in range(3): char['stats'][random.choice(list(char['stats'].keys()))] += 1
            xp_needed = self._get_xp_for_next_level(char['level'])

        if leveled_up:
            await message.channel.send(f"🎉 **{char['name']}** (ID: {char_id}) leveled up to **Level {char['level']}**!")

            # Check for newly unlocked moves
            newly_unlocked = self._get_unlocked_attacks(char, char['level'])
            current_moveset_names = {move for move in char.get('moveset', [])}
            
            for new_move in newly_unlocked:
                if new_move['name'] not in current_moveset_names:
                    # A new move has been unlocked!
                    await message.channel.send(f"✨ **{char['name']}** unlocked a new move: **{new_move['name']}** at level {char['level']}!")
        
        db.update_player(message.author.id, player)

async def setup(bot):
    cog = CZ(bot)
    for command in cog.get_commands():
        if not hasattr(command, 'category'):
            if command.name == 'moves':
                command.category = "Team"
            else:
                command.category = 'Fun'
    
    if not cog.characters:
        print("❌ Critical Error: Could not load RPG cog due to missing characters.json data.")
    else:
        await bot.add_cog(cog)
