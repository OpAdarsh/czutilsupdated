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

    @commands.command(name='pull', aliases=['p'], help="!pull - Get a free random character every 5 minutes.", category="Economic")
    @has_accepted_rules()
    async def pull(self, ctx):
        cz_cog = self.bot.get_cog('Core Gameplay')
        stats_cog = self.bot.get_cog('Stat Calculations')
        if not cz_cog or not stats_cog:
            await ctx.send("Game systems are currently offline. Please try again later."); return

        player = db.get_player(ctx.author.id)
        
        cooldown = 300  # 5 minutes
        time_since_last_pull = time.time() - player.get('last_pull_time', 0)

        if time_since_last_pull < cooldown:
            remaining_time = cooldown - time_since_last_pull
            await ctx.send(f"You're on cooldown! Please wait {int(remaining_time // 60)}m {int(remaining_time % 60)}s."); return

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
        player['last_pull_time'] = time.time()
        
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You pulled a **Lvl {random_level} {char_name}** with **{new_char_instance['iv']}% IV**! Use `!info latest` to see their stats.")

    @commands.command(name='sell', help="!sell <id_or_name> - Sells a character for coins.", category="Economic")
    @has_accepted_rules()
    async def sell(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return

        if char_id == player.get('selected_character_id'):
            await ctx.send("You cannot sell your currently selected character. Use `!select` to change it first."); return
        if char_id in player.get('team', {}).values():
            await ctx.send("You cannot sell a character that is on your team. Use `!team remove` first."); return

        character_to_sell = player['characters'][char_id]
        sale_price = 10 + (character_to_sell['level'] * 2) + round(character_to_sell['iv'] / 5)
        
        del player['characters'][char_id]
        player['coins'] += sale_price
        
        db.update_player(ctx.author.id, player)
        await ctx.send(f"You sold **{character_to_sell['name']}** for **{sale_price}** coins.")

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

    @commands.command(name='allcharacters', aliases=['chars', 'characters'], help="!allcharacters [sort_key] - View all characters.", category="Economic")
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

    @commands.command(name='info', aliases=['i'], help="!info [latest|id_or_name] - Shows info for a character.", category="Economic")
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
            
    @commands.command(name='collection', aliases=['col'], help="!collection - View your character collection.", category="Economic")
    @has_accepted_rules()
    async def collection(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['characters']:
            await ctx.send("Your collection is empty!"); return
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Collection", color=discord.Color.purple())
        team_char_ids = player.get('team', {}).values()
        desc = "".join([f"`{cid}`: **Lvl {c['level']} {c['name']}** ({c['iv']}% IV) {'🛡️' if cid in team_char_ids else ''}{'⭐' if cid == player['selected_character_id'] else ''}\n" for cid, c in player['characters'].items()])
        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(name='inventory', aliases=['inv'], help="!inventory - View your items.", category="Economic")
    @has_accepted_rules()
    async def inventory(self, ctx):
        player = db.get_player(ctx.author.id)
        if not player['inventory']:
            await ctx.send("Your inventory is empty."); return
        embed = discord.Embed(title="Your Inventory", color=discord.Color.orange())
        embed.description = "\n".join(f"**{name}**: x{count}" for name, count in player['inventory'].items())
        await ctx.send(embed=embed)

    @commands.command(name='select', help="!select <id_or_name> - Select your active character.", category="Team")
    @has_accepted_rules()
    async def select(self, ctx, *, identifier: str):
        player = db.get_player(ctx.author.id)
        char_id = await self._find_character_from_input(ctx, player, identifier)
        if char_id is None: return

        player['selected_character_id'] = char_id
        db.update_player(ctx.author.id, player)
        await ctx.send(f"✅ You have selected **{player['characters'][char_id]['name']}** (ID: {char_id}) to gain XP.")

    @commands.group(name='team', aliases=['t'], invoke_without_command=True, help="!team - Manages your 3-slot team.", category="Team")
    @has_accepted_rules()
    async def team(self, ctx):
        await self.view_team(ctx)

    @team.command(name='view', aliases=['v'], help="!team view - View your active team.", category="Team")
    @has_accepted_rules()
    async def view_team(self, ctx):
        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})
        
        embed = discord.Embed(title="Your Active Team", color=discord.Color.green())
        
        for slot, char_id in team_slots.items():
            if char_id:
                char_info = player['characters'].get(char_id)
                if char_info:
                    embed.add_field(name=f"Slot {slot}", value=f"**{char_info['name']}** (ID: {char_id})\nLvl {char_info['level']}, IV: {char_info['iv']}%", inline=False)
                else:
                    embed.add_field(name=f"Slot {slot}", value=f"Invalid Character (ID: {char_id})", inline=False)
            else:
                embed.add_field(name=f"Slot {slot}", value="Empty", inline=False)
                
        await ctx.send(embed=embed)

    @team.command(name='add', help="!team add <slot> <id_or_name> - Adds a character to a team slot.", category="Team")
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
        
        if char_id in team_slots.values():
            await ctx.send("This character is already on your team in another slot."); return

        team_slots[slot] = char_id
        player['team'] = team_slots
        db.update_player(ctx.author.id, player)
        await ctx.send(f"Added **{player['characters'][char_id]['name']}** to team slot {slot}.")
        await self.view_team(ctx)

    @team.command(name='remove', aliases=['r'], help="!team remove <slot> - Removes a character from a team slot.", category="Team")
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

    @team.command(name='swap', help="!team swap <slot> <id_or_name> - Swaps a character into a team slot.", category="Team")
    @has_accepted_rules()
    async def team_swap(self, ctx, slot: str, *, identifier: str):
        if slot not in ['1', '2', '3']:
            await ctx.send("Invalid slot. Please choose 1, 2, or 3."); return
            
        player = db.get_player(ctx.author.id)
        team_slots = player.get('team', {'1': None, '2': None, '3': None})

        char_id_to_add = await self._find_character_from_input(ctx, player, identifier)
        if char_id_to_add is None: return

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

    @commands.command(name='equip', aliases=['eq'], help="!equip <id_or_name>, <item_name> - Equips an item.", category="Team")
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

    @commands.command(name='unequip', aliases=['ue'], help="!unequip <id_or_name> - Unequips an item.", category="Team")
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

    @commands.group(name='moves', aliases=['m'], invoke_without_command=True, help="!moves [id_or_name] - Manage character moves.", category="Team")
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
        active_moves_names = character.get('moveset', [])
        
        active_moves_details = [f"**{m['name']}** - Power: {m.get('power', 0)}, Acc: {m.get('accuracy', 100)}%"
                                for m_name in active_moves_names
                                if (m := next((m for m in self.attacks.get('physical', []) + self.attacks.get('special', []) + all_special_moves if m['name'] == m_name), None))]
        embed.add_field(name="⚔️ Active Moveset", value="\n".join(active_moves_details) or "None", inline=False)

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

        embed.set_footer(text="Use `!moves swap <id_or_name>, <new_move>, <old_move>`")
        await ctx.send(embed=embed)

    @moves.command(name='swap', help="!moves swap <id_or_name>, <new>, <old> - Swaps moves.", category="Team")
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

async def setup(bot):
    await bot.add_cog(CharacterManagement(bot))

