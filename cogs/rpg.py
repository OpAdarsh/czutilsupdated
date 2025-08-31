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

        cog = ctx.bot.get_cog('Core Gameplay')
        if not cog:
            return False

        # Check if user already has a pending rules prompt
        if ctx.author.id in cog.rules_prompts.values():
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

        cog.rules_prompts[prompt_message.id] = ctx.author.id

        await ctx.send("Please accept the rules above to continue.", delete_after=10)
        return False

    return commands.check(predicate)

class CZ(commands.Cog, name="Core Gameplay"):
    """A cog for the anime RPG game's core mechanics."""
    def __init__(self, bot):
        self.bot = bot
        self.characters = load_json_data('characters.json')
        self.attacks = load_json_data('attacks.json')
        self.active_battles = {}
        self.rules_prompts = {}
        # Initialize database first
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

    def _create_character_instance(self, base_character):
        stats_cog = self.bot.get_cog('Stat Calculations')
        if not stats_cog:
            print("Error: Stat Calculations cog not found.")
            return None

        stat_keys = ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']
        base_stats = {k: v for k, v in base_character.items() if k in stat_keys}

        individual_ivs = stats_cog._generate_ivs_with_distribution(list(base_stats.keys()))

        total_iv_points = sum(individual_ivs.values())
        max_possible_iv_points = 31 * len(base_stats)
        iv_percentage = round((total_iv_points / max_possible_iv_points) * 100, 2) if max_possible_iv_points > 0 else 0

        instance_stats = stats_cog._calculate_stats(base_stats, individual_ivs, 1)

        # Get 2 common physical moves and 1 special move
        physical_moves = [move['name'] for move in self.attacks.get('physical', [])[:2]]
        special_moves = [move['name'] for move in self.attacks.get('special', [])[:1]]
        char_id_str = str(base_character.get('id'))
        first_special = next((move['name'] for move in self.attacks.get('characters', {}).get(char_id_str, []) if move.get('unlock_level', 1) <= 1), None)

        initial_moveset = physical_moves + special_moves
        if first_special: initial_moveset.append(first_special)
        
        # Ensure moveset has exactly 4 slots (pad with None if needed)
        while len(initial_moveset) < 4:
            initial_moveset.append(None)

        return {
            "id": base_character.get('id'), "name": base_character['name'], "iv": iv_percentage, "stats": instance_stats,
            "ability": base_character['Ability'], "description": base_character['Description'],
            "equipped_item": None, "level": 1, "xp": 0, "moveset": initial_moveset,
            "individual_ivs": individual_ivs
        }

    def get_character_attacks(self, character):
        active_moves = character.get('moveset', [])
        # Filter out None values from moveset
        active_moves = [move for move in active_moves if move is not None]
        all_possible_moves = self.attacks.get('physical', []) + self.attacks.get('special', []) + self.attacks.get('characters', {}).get(str(character.get('id')), [])
        return [m for m in all_possible_moves if m['name'] in active_moves]

    # --- Battle UI Components ---
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
                        await interaction.response.send_message("This isn't your turn!", ephemeral=True); return
                    self.chosen_attack = atk
                    self.stop()
                    await interaction.response.defer()
                button.callback = button_callback
                self.add_item(button)
        async def on_timeout(self):
            if self.available_attacks: self.chosen_attack = self.available_attacks[0]
            self.stop()

    class CharacterSelectView(discord.ui.View):
        def __init__(self, author, team):
            super().__init__(timeout=120.0)
            self.author = author
            self.team = [c for c in team if c['current_hp'] > 0]
            self.selected_character = None
            for character in self.team:
                button = discord.ui.Button(label=f"{character['name']} (HP: {character['current_hp']}/{character['stats']['HP']})", style=discord.ButtonStyle.secondary)
                async def button_callback(interaction: discord.Interaction, char=character):
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("This isn't your battle!", ephemeral=True); return
                    self.selected_character = char
                    self.stop()
                    await interaction.response.defer()
                button.callback = button_callback
                self.add_item(button)
        async def on_timeout(self):
            if self.team: self.selected_character = self.team[0]
            self.stop()

    class EndBattleView(discord.ui.View):
        def __init__(self, opponent):
            super().__init__(timeout=30.0)
            self.opponent = opponent
            self.agreed = False

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user.id == self.opponent.id

        @discord.ui.button(label="Agree to End", style=discord.ButtonStyle.green)
        async def agree(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.agreed = True
            await interaction.response.send_message("You have agreed to end the battle.", ephemeral=True)
            self.stop()

        @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
        async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("You have declined to end the battle.", ephemeral=True)
            self.stop()

    @commands.command(name='battle', help="!battle <member> - Challenge another player to a battle.", category="Battle System")
    @has_accepted_rules()
    async def battle(self, ctx, opponent: discord.Member):
        challenger = ctx.author
        if challenger == opponent:
            await ctx.send("You can't challenge yourself!"); return
        if opponent.bot:
            await ctx.send("You cannot battle bots with this command. Use `!battlecz` to fight an AI."); return

        battle_key = tuple(sorted((challenger.id, opponent.id)))
        if battle_key in self.active_battles:
            await ctx.send("One of you is already in a battle!"); return

        challenger_player, opponent_player = db.get_player(challenger.id), db.get_player(opponent.id)
        if not challenger_player['team']:
            await ctx.send("You need a team first."); return
        if not opponent_player['team']:
            await ctx.send(f"{opponent.display_name} does not have a team."); return

        req_msg = await ctx.send(f"{opponent.mention}, you've been challenged by {challenger.display_name}! React with ✅ to accept.")
        await req_msg.add_reaction('✅'); await req_msg.add_reaction('❌')

        def check(r, u): return u == opponent and str(r.emoji) in ['✅', '❌'] and r.message.id == req_msg.id
        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == '❌':
                await req_msg.edit(content=f"{opponent.display_name} declined the battle."); return
        except asyncio.TimeoutError:
            await req_msg.edit(content="Battle request timed out."); return

        await req_msg.delete()

        task = asyncio.create_task(self._run_interactive_battle(ctx, challenger, opponent, challenger_player, opponent_player))
        self.active_battles[battle_key] = {"task": task, "channel": ctx.channel}

    async def _get_player_move(self, user, active_char, ctx):
        """Prompts a player for their attack via DM."""
        available_attacks = self.get_character_attacks(active_char)
        view = self.BattleView(user, available_attacks)

        try:
            prompt_msg = await user.send(f"Choose an attack for **{active_char['name']}**.", view=view)
        except discord.Forbidden:
            prompt_msg = await ctx.send(f"{user.mention}, I can't DM you! Please choose your move here.", view=view, delete_after=60.0)

        await view.wait()
        return view.chosen_attack

    async def _prompt_character_selection(self, user, team, ctx, prompt_text):
        if not team:
            return None

        view = self.CharacterSelectView(user, team)
        embed = discord.Embed(title="Character Selection", description=prompt_text, color=user.color or discord.Color.default())
        prompt_message = await ctx.send(content=user.mention, embed=embed, view=view)

        await view.wait()
        try: 
            await prompt_message.delete()
        except discord.NotFound: 
            pass

        return view.selected_character

    async def _run_interactive_battle(self, ctx, p1_user, p2_user, p1_data, p2_data):
        stats_cog = self.bot.get_cog('Stat Calculations')
        if not stats_cog:
            await ctx.send("Battle system is offline, stat module not loaded."); return

        battle_key = tuple(sorted((p1_user.id, p2_user.id)))
        battle_message = None

        try:
            def prep_team(player_data):
                team = []
                team_slots = player_data.get('team', {})
                for slot, char_id in team_slots.items():
                    if char_id and char_id in player_data['characters']:
                        inst = player_data['characters'][char_id].copy()
                        inst['stats'] = stats_cog.get_character_display_stats(inst)
                        inst['current_hp'] = inst['stats']['HP']
                        team.append(inst)
                return team

            team1, team2 = prep_team(p1_data), prep_team(p2_data)
            players = {p1_user.id: {"team": team1, "user": p1_user}, p2_user.id: {"team": team2, "user": p2_user}}

            p1_active_char_task = self._prompt_character_selection(p1_user, team1, ctx, f"Choose your starting character!")
            p2_active_char_task = self._prompt_character_selection(p2_user, team2, ctx, f"Choose your starting character!")
            p1_active_char, p2_active_char = await asyncio.gather(p1_active_char_task, p2_active_char_task)

            if p1_active_char is None or p2_active_char is None:
                await ctx.send("A player failed to select a character, battle cancelled.")
                return

            players[p1_user.id]["active"] = p1_active_char
            players[p2_user.id]["active"] = p2_active_char

            log = [f"{p1_user.display_name} sends out **{p1_active_char['name']}**!", f"{p2_user.display_name} sends out **{p2_active_char['name']}**!"]
            battle_message = await ctx.send(embed=self._create_battle_embed(log, team1, team2, p1_user, p2_user, p1_active_char, p2_active_char))

            while all(any(c['current_hp'] > 0 for c in p['team']) for p in players.values()):
                log = ["--- New Round ---"]
                embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, p1_active_char, p2_active_char)
                await battle_message.edit(embed=embed, view=None)

                p1_action = await self._get_player_move(p1_user, p1_active_char, ctx)
                p2_action = await self._get_player_move(p2_user, p2_active_char, ctx)

                actions = [
                    {'user_id': p1_user.id, 'attack': p1_action, 'active': p1_active_char, 'target': p2_active_char},
                    {'user_id': p2_user.id, 'attack': p2_action, 'active': p2_active_char, 'target': p1_active_char}
                ]
                actions.sort(key=lambda x: x['active']['stats']['SPD'], reverse=True)

                for turn_data in actions:
                    attacker_player = players[turn_data['user_id']]
                    if attacker_player['active']['current_hp'] <= 0: continue

                    defender = turn_data['target']
                    if defender['current_hp'] <= 0:
                        log.append(f"▶️ {attacker_player['active']['name']}'s target was already defeated!"); continue

                    chosen_attack = turn_data['attack']
                    if not chosen_attack:
                        log.append(f"▶️ {attacker_player['user'].display_name}'s action failed due to timeout."); continue

                    log.append(f"▶️ {attacker_player['active']['name']} uses **{chosen_attack['name']}** on {defender['name']}!")
                    if random.randint(1, 100) > chosen_attack.get('accuracy', 100):
                        log.append("💨 The attack missed!")
                    else:
                        dmg = stats_cog.calculate_damage(attacker_player['active'], defender, chosen_attack)
                        defender['current_hp'] = max(0, defender['current_hp'] - dmg['damage'])
                        log.append(f"💥 It hits for **{dmg['damage']}** damage!{' **CRITICAL HIT!**' if dmg['crit'] else ''}")

                        if defender['current_hp'] == 0:
                            log.append(f"💀 {defender['name']} has been defeated!")

                            opponent_id = p2_user.id if turn_data['user_id'] == p1_user.id else p1_user.id
                            remaining = [c for c in players[opponent_id]['team'] if c['current_hp'] > 0]
                            if not remaining: break

                            new_char = await self._prompt_character_selection(players[opponent_id]['user'], remaining, ctx, "Your character fainted! Choose your next one.")
                            players[opponent_id]['active'] = new_char
                            if opponent_id == p1_user.id: p1_active_char = new_char
                            else: p2_active_char = new_char
                            log.append(f"{players[opponent_id]['user'].display_name} sends out **{new_char['name']}**!")

                embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, p1_active_char, p2_active_char)
                await battle_message.edit(embed=embed)
                await asyncio.sleep(4)

            winner = p1_user if any(c['current_hp'] > 0 for c in team1) else p2_user
            final_embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, p1_active_char, p2_active_char)
            final_embed.title = f"🏆 Winner: {winner.display_name}! 🏆"
            await battle_message.edit(embed=final_embed, view=None)

        except asyncio.CancelledError:
            log.append("Battle ended by mutual agreement.")
            final_embed = self._create_battle_embed(log, team1, team2, p1_user, p2_user, p1_active_char, p2_active_char)
            final_embed.title = "🤝 Battle Ended in a Draw 🤝"
            await battle_message.edit(embed=final_embed, view=None)

        except Exception as e:
            print(f"An error occurred during battle: {e}")
            await ctx.send("An unexpected error occurred and the battle has been cancelled.")

        finally:
            if battle_key in self.active_battles:
                del self.active_battles[battle_key]

    def _create_hp_bar(self, current, max_val, length=15):
        if max_val <= 0: return f"`[{' ' * length}]` 0%"
        percent = max(0, min(1, current / max_val))
        filled_length = int(length * percent)
        
        # Color coding based on HP percentage
        if percent > 0.7:
            bar_char = '🟩'
        elif percent > 0.3:
            bar_char = '🟨'
        else:
            bar_char = '🟥'
            
        empty_char = '⬜'
        bar = bar_char * filled_length + empty_char * (length - filled_length)
        percentage = int(percent * 100)
        return f"{bar} {percentage}%"

    def _create_battle_embed(self, log, t1, t2, p1_user, p2_user, p1_active, p2_active, footer_text=None):
        embed = discord.Embed(title=f"⚔️ {p1_user.display_name} vs {p2_user.display_name}", color=discord.Color.red())

        # Active fighters section
        if p1_active and p2_active:
            p1_hp_bar = self._create_hp_bar(p1_active['current_hp'], p1_active['stats']['HP'])
            p2_hp_bar = self._create_hp_bar(p2_active['current_hp'], p2_active['stats']['HP'])
            
            active_display = f"🥊 **{p1_active['name']}** (Lv.{p1_active['level']})\n{p1_hp_bar}\n"
            active_display += f"⚡ ATK: {p1_active['stats']['ATK']} | DEF: {p1_active['stats']['DEF']} | SPD: {p1_active['stats']['SPD']}\n\n"
            active_display += f"🥊 **{p2_active['name']}** (Lv.{p2_active['level']})\n{p2_hp_bar}\n"
            active_display += f"⚡ ATK: {p2_active['stats']['ATK']} | DEF: {p2_active['stats']['DEF']} | SPD: {p2_active['stats']['SPD']}"
            
            embed.add_field(name="🔥 Active Fighters", value=active_display, inline=False)

        # Team status (more compact)
        for user, team, active_char in [(p1_user, t1, p1_active), (p2_user, t2, p2_active)]:
            team_status = []
            for i, c in enumerate(team, 1):
                active_indicator = "🟢" if c is active_char and c['current_hp'] > 0 else "⚪"
                status = "💀" if c['current_hp'] <= 0 else f"{round(c['current_hp'])}/{c['stats']['HP']}"
                team_status.append(f"{active_indicator} **{c['name']}** `{status}`")
            embed.add_field(name=f"🛡️ {user.display_name}'s Team", value="\n".join(team_status) or "Defeated", inline=True)

        # Enhanced battle log
        if log:
            formatted_log = []
            for entry in log[-8:]:  # Show more log entries
                if "uses" in entry:
                    formatted_log.append(f"⚔️ {entry}")
                elif "damage" in entry:
                    formatted_log.append(f"💥 {entry}")
                elif "defeated" in entry or "fainted" in entry:
                    formatted_log.append(f"💀 {entry}")
                elif "sends out" in entry:
                    formatted_log.append(f"🔄 {entry}")
                elif "missed" in entry:
                    formatted_log.append(f"💨 {entry}")
                else:
                    formatted_log.append(f"📢 {entry}")
            
            embed.add_field(name="📜 Battle Log", value=">>> " + "\n".join(formatted_log) or "Battle starts!", inline=False)
        
        if footer_text:
            embed.set_footer(text=footer_text)
        return embed

    @commands.command(name='battleend', help="!battleend - Propose to end the current battle.", category="Battle System")
    async def battle_end(self, ctx):
        battle_key = None
        opponent = None

        for key in self.active_battles.keys():
            if ctx.author.id in key:
                battle_key = key
                opponent_id = key[1] if key[0] == ctx.author.id else key[0]
                opponent = await self.bot.fetch_user(opponent_id)
                break

        if not battle_key or not opponent:
            await ctx.send("You are not currently in a battle."); return

        view = self.EndBattleView(opponent)
        await ctx.send(f"{opponent.mention}, {ctx.author.display_name} has proposed to end the battle. Do you agree?", view=view)

        await view.wait()
        if view.agreed:
            task = self.active_battles[battle_key]['task']
            task.cancel()
            await ctx.send("Both players have agreed. The battle has been ended.")
        else:
            await ctx.send(f"{opponent.display_name} has declined to end the battle.")

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
        char['xp'] += random.randint(15, 25)
        xp_needed = self._get_xp_for_next_level(char['level'])

        leveled_up = False
        while char['xp'] >= xp_needed:
            if char['level'] >= 100: 
                char['xp'] = 0; break
            char['level'] += 1
            char['xp'] -= xp_needed
            leveled_up = True
            xp_needed = self._get_xp_for_next_level(char['level'])

        if leveled_up:
            stats_cog = self.bot.get_cog('Stat Calculations')
            base_char_data = self.characters.get(char['name'])
            if base_char_data and stats_cog:
                stat_keys = ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']
                base_stats = {k: v for k, v in base_char_data.items() if k in stat_keys}
                char['stats'] = stats_cog._calculate_stats(base_stats, char['individual_ivs'], char['level'])

            await message.channel.send(f"🎉 **{char['name']}** (ID: {char['id']}) leveled up to **Level {char['level']}**!")

            all_special_moves = self.attacks.get('characters', {}).get(str(char.get('id')), [])
            newly_unlocked = [move for move in all_special_moves if old_level < move['unlock_level'] <= char['level']]

            if newly_unlocked:
                for new_move in newly_unlocked:
                    await message.channel.send(f"✨ **{char['name']}** unlocked a new move: **{new_move['name']}**!")

        db.update_player(message.author.id, player)

async def setup(bot):
    cog = CZ(bot)
    if not cog.characters:
        print("❌ Critical Error: Could not load RPG cog due to missing characters.json data.")
    else:
        await bot.add_cog(cog)