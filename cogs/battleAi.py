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

        # This check is a failsafe; the prompt is handled by the Core Gameplay cog.
        await ctx.send("You must accept the rules first. The rules prompt will be shown on your next command.")
        return False

    return commands.check(predicate)


class BattleAI(commands.Cog, name="AI Battle"):
    """A cog for players to battle against a computer-controlled opponent."""
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = set()
        self.characters = load_json_data('characters.json')
        self.attacks = load_json_data('attacks.json')
        
    def get_character_attacks(self, character):
        """Fetches the list of available attacks for a character instance."""
        active_moves = character.get('moveset', [])
        # Filter out None values from moveset and ensure we have at least some moves
        active_moves = [move for move in active_moves if move is not None]
        
        # Get all possible moves
        physical_moves = self.attacks.get('physical', [])
        special_moves = self.attacks.get('special', [])
        character_moves = self.attacks.get('characters', {}).get(str(character.get('id', character.get('name', ''))), [])
        
        all_possible_moves = physical_moves + special_moves + character_moves
        
        # Get available attacks
        available_attacks = [m for m in all_possible_moves if m['name'] in active_moves]
        
        # Fallback to basic attacks if no moves found
        if not available_attacks and physical_moves:
            available_attacks = [physical_moves[0]]  # Use first basic attack as fallback
            
        return available_attacks

    # --- Battle UI Components (Copied from rpg.py for consistency) ---
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
            
    # --- Battle Command ---
    @commands.command(name='battlecz', help="!battlecz - Battle against an AI opponent.", category="Battle")
    @has_accepted_rules()
    async def battle_cz(self, ctx):
        challenger = ctx.author
        player_data = db.get_player(challenger.id)

        team_slots = player_data.get('team', {})
        if not any(char_id for char_id in team_slots.values() if char_id):
            await ctx.send("You need a team to battle! Use `!team add` to add characters first."); return
        if player_data['coins'] < 20:
            await ctx.send("You need at least 20 coins to start an AI battle."); return
        if challenger.id in self.active_battles:
            await ctx.send("You are already in a battle!"); return

        stats_cog = self.bot.get_cog('Stat Calculations')
        if not stats_cog:
            await ctx.send("Game systems are currently offline (Stats module not loaded)."); return

        team_slots = player_data.get('team', {})
        team_levels = [player_data['characters'][cid]['level'] for cid in team_slots.values() if cid and cid in player_data['characters']]
        avg_level = max(1, sum(team_levels) // len(team_levels)) if team_levels else 1
        
        bot_team_chars = random.sample(list(self.characters.items()), 3)
        bot_team = []
        for name, data in bot_team_chars:
            scaled_char = stats_cog._scale_character_to_level({"name": name, **data}, avg_level)
            
            # Ensure bot characters have movesets
            if not scaled_char.get('moveset') or not any(move for move in scaled_char.get('moveset', []) if move is not None):
                # Give them basic physical attacks
                basic_moves = self.attacks.get('physical', [])
                if basic_moves:
                    scaled_char['moveset'] = [basic_moves[0]['name'], None, None, None]
                    if len(basic_moves) > 1:
                        scaled_char['moveset'][1] = basic_moves[1]['name']
            
            bot_team.append(scaled_char)

        await self._run_ai_battle(ctx, challenger, player_data, bot_team)

    async def _prompt_character_selection(self, ctx, user, team, prompt_text):
        view = self.CharacterSelectView(user, team)
        embed = discord.Embed(title="Character Selection", description=prompt_text, color=user.color or discord.Color.default())
        prompt_message = await ctx.send(content=user.mention, embed=embed, view=view)
        
        await view.wait()
        try: await prompt_message.delete()
        except discord.NotFound: pass
        
        return view.selected_character
        
    async def _get_player_move(self, ctx, user, active_char):
        available_attacks = self.get_character_attacks(active_char)
        view = self.BattleView(user, available_attacks)
        
        prompt_msg = await ctx.send(f"{user.mention}, choose an attack for **{active_char['name']}**.", view=view, delete_after=60.0)
        
        await view.wait()
        return view.chosen_attack

    async def _run_ai_battle(self, ctx, user, user_data, bot_team):
        self.active_battles.add(user.id)
        stats_cog = self.bot.get_cog('Stat Calculations')
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
                        
                        # Ensure character has a proper moveset for battle
                        if not inst.get('moveset') or not any(move for move in inst.get('moveset', []) if move is not None):
                            # Give basic moves if character has none
                            basic_moves = self.attacks.get('physical', [])
                            if basic_moves:
                                inst['moveset'] = [basic_moves[0]['name'], None, None, None]
                        
                        team.append(inst)
                return team

            user_team = prep_team(user_data)
            
            user_active_char = await self._prompt_character_selection(ctx, user, user_team, "Choose your starting character!")
            bot_active_char = random.choice(bot_team)
            
            log = [f"{user.display_name} sends out **{user_active_char['name']}**!", f"The AI sends out **{bot_active_char['name']}**!"]
            battle_message = await ctx.send(embed=self._create_battle_embed(log, user_team, bot_team, user, self.bot.user, user_active_char, bot_active_char))

            while any(c['current_hp'] > 0 for c in user_team) and any(c['current_hp'] > 0 for c in bot_team):
                log = ["--- New Round ---"]
                
                user_action = await self._get_player_move(ctx, user, user_active_char)
                
                bot_attacks = self.get_character_attacks(bot_active_char)
                if not bot_attacks:
                    # Fallback to basic attack if no moves available
                    bot_attacks = self.attacks.get('physical', [])
                    if not bot_attacks:
                        log.append("❌ Bot has no available attacks - skipping turn")
                        continue
                        
                bot_action = max(bot_attacks, key=lambda m: m.get('power', 0)) if bot_attacks else None
                
                actions = [
                    {'user': user, 'attack': user_action, 'active': user_active_char, 'target': bot_active_char},
                    {'user': self.bot.user, 'attack': bot_action, 'active': bot_active_char, 'target': user_active_char}
                ]
                actions.sort(key=lambda x: x['active']['stats']['SPD'], reverse=True)

                for turn_data in actions:
                    attacker = turn_data['active']
                    defender = turn_data['target']
                    
                    if attacker['current_hp'] <= 0 or defender['current_hp'] <= 0: continue
                    
                    chosen_attack = turn_data['attack']
                    if not chosen_attack:
                        log.append(f"▶️ {turn_data['user'].display_name}'s action failed due to timeout."); continue

                    log.append(f"▶️ {attacker['name']} uses **{chosen_attack['name']}** on {defender['name']}!")
                    if random.randint(1, 100) > chosen_attack.get('accuracy', 100):
                        log.append("💨 The attack missed!")
                    else:
                        dmg = stats_cog.calculate_damage(attacker, defender, chosen_attack)
                        defender['current_hp'] = max(0, defender['current_hp'] - dmg['damage'])
                        log.append(f"💥 It hits for **{dmg['damage']}** damage!{' **CRITICAL HIT!**' if dmg['crit'] else ''}")
                        
                        if defender['current_hp'] == 0:
                            log.append(f"💀 {defender['name']} has been defeated!")
                            
                            if defender is bot_active_char:
                                remaining_bots = [c for c in bot_team if c['current_hp'] > 0]
                                if not remaining_bots: break
                                bot_active_char = random.choice(remaining_bots)
                                log.append(f"The AI sends out **{bot_active_char['name']}**!")
                            else:
                                remaining_user_chars = [c for c in user_team if c['current_hp'] > 0]
                                if not remaining_user_chars: break
                                user_active_char = await self._prompt_character_selection(ctx, user, remaining_user_chars, "Your character fainted! Choose your next one.")
                                log.append(f"{user.display_name} sends out **{user_active_char['name']}**!")

                embed = self._create_battle_embed(log, user_team, bot_team, user, self.bot.user, user_active_char, bot_active_char)
                await battle_message.edit(embed=embed)
                await asyncio.sleep(4)

            winner_is_user = any(c['current_hp'] > 0 for c in user_team)
            
            final_embed = self._create_battle_embed(log, user_team, bot_team, user, self.bot.user, user_active_char, bot_active_char)
            player = db.get_player(user.id)
            if winner_is_user:
                final_embed.title = "🏆 You Won! 🏆"
                final_embed.description = "You defeated the AI and earned **50** coins!"
                player['coins'] += 50
            else:
                final_embed.title = "☠️ You Lost! ☠️"
                final_embed.description = "The AI was victorious. You lost **20** coins."
                player['coins'] -= 20
            
            db.update_player(user.id, player)
            final_embed.set_footer(text=f"Your new balance: {player['coins']} coins")
            await battle_message.edit(embed=final_embed, view=None)
        
        except Exception as e:
            print(f"An error occurred during AI battle: {e}")
            await ctx.send("An unexpected error occurred during the battle. The match has been concluded.")
        
        finally:
            self.active_battles.remove(user.id)

    def _create_hp_bar(self, current, max_val, length=10):
        if max_val <= 0: return f"`[{' ' * length}]`"
        percent = max(0, min(1, current / max_val))
        filled_length = int(length * percent)
        bar = '█' * filled_length + '─' * (length - filled_length)
        return f"`[{bar}]`"

    def _create_battle_embed(self, log, t1, t2, p1_user, p2_user, p1_active, p2_active, footer_text=None):
        embed = discord.Embed(title=f"⚔️ {p1_user.display_name} vs {p2_user.display_name}", color=discord.Color.red())
        
        for user, team, active_char in [(p1_user, t1, p1_active), (p2_user, t2, p2_active)]:
            team_status = []
            for c in team:
                hp_bar = self._create_hp_bar(c['current_hp'], c['stats']['HP'])
                active_indicator = "▶️" if c is active_char and c['current_hp'] > 0 else ""
                status = "KO" if c['current_hp'] <= 0 else f"{round(c['current_hp'])}/{c['stats']['HP']}"
                team_status.append(f"{active_indicator}**{c['name']}**: {hp_bar} `{status}`")
            embed.add_field(name=f"{user.display_name}'s Team", value="\n".join(team_status) or "Defeated", inline=False)
            
        embed.add_field(name="Battle Log", value=">>> " + "\n".join(log[-5:]) or "Battle starts!", inline=False)
        if footer_text:
            embed.set_footer(text=footer_text)
        return embed

async def setup(bot):
    await bot.add_cog(BattleAI(bot))

