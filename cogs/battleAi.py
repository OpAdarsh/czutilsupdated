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
        self.ranks = load_json_data('ranks.json')
        
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

    def _generate_ai_moveset(self, character, character_name):
        """Generates an optimal moveset for AI characters based on their level."""
        # Get all available moves for this character
        basic_physical = self.attacks.get('physical', [])
        basic_special = self.attacks.get('special', [])
        character_moves = self.attacks.get('characters', {}).get(character_name, [])
        
        # Start with a basic moveset
        moveset = [None, None, None, None]
        
        # Always give at least one basic physical attack
        if basic_physical:
            moveset[0] = basic_physical[0]['name']
        
        # Add character-specific moves based on level
        unlocked_moves = [m for m in character_moves if m.get('unlock_level', 1) <= character['level']]
        
        if unlocked_moves:
            # Sort moves by power and unlock level for optimal selection
            unlocked_moves.sort(key=lambda m: (m.get('power', 0), m.get('unlock_level', 1)), reverse=True)
            
            # Fill remaining slots with best available moves
            slot_index = 1
            for move in unlocked_moves:
                if slot_index >= 4:
                    break
                if move['name'] not in moveset:
                    moveset[slot_index] = move['name']
                    slot_index += 1
        
        # Fill any remaining empty slots with basic attacks
        if len(basic_physical) > 1 and moveset[1] is None:
            moveset[1] = basic_physical[1]['name'] if len(basic_physical) > 1 else basic_physical[0]['name']
        
        if basic_special and moveset[2] is None:
            moveset[2] = basic_special[0]['name']
        
        # If still empty slots, add more basic moves
        if moveset[3] is None and len(basic_physical) > 2:
            moveset[3] = basic_physical[2]['name']
        elif moveset[3] is None and len(basic_special) > 1:
            moveset[3] = basic_special[1]['name']
        
        return moveset

    def _select_ai_move(self, ai_char, target_char, available_attacks):
        """Selects the best move for AI based on battle situation."""
        if not available_attacks:
            return None
        
        # Calculate effectiveness for each move
        move_scores = []
        ai_hp_percent = ai_char['current_hp'] / ai_char['stats']['HP']
        target_hp_percent = target_char['current_hp'] / target_char['stats']['HP']
        
        for move in available_attacks:
            score = move.get('power', 0)
            
            # Bonus for high accuracy moves
            accuracy = move.get('accuracy', 100)
            score += (accuracy - 85) * 0.5  # Bonus for >85% accuracy
            
            # Prefer powerful moves when enemy is low on HP
            if target_hp_percent < 0.3:
                score += move.get('power', 0) * 0.5
            
            # Prefer defensive/healing moves when AI is low on HP
            if ai_hp_percent < 0.4:
                if 'heal' in move.get('name', '').lower() or move.get('type') == 'heal':
                    score += 50
                elif move.get('power', 0) < 60:  # Prefer safer moves when low
                    score += 20
            
            # Type effectiveness consideration (basic)
            move_type = move.get('type', '').lower()
            if move_type in ['fire', 'water', 'electric', 'psychic']:
                score += 10  # Slight bonus for elemental moves
            
            # Add some randomness to prevent predictability
            score += random.randint(-10, 10)
            
            move_scores.append((move, score))
        
        # Select the highest scoring move
        best_move = max(move_scores, key=lambda x: x[1])[0]
        return best_move

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
            
            # Advanced AI moveset learning - give them optimal movesets based on their level
            scaled_char['moveset'] = self._generate_ai_moveset(scaled_char, name)
            
            # Initialize current_hp for battle
            scaled_char['current_hp'] = scaled_char['stats']['HP']
            
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
                
                # Smart AI move selection based on situation
                bot_action = self._select_ai_move(bot_active_char, user_active_char, bot_attacks)
                
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
            
            # Calculate rank changes
            old_rp = player.get('rank_points', 0)
            old_rank, old_rank_data = self.get_player_rank(old_rp)
            
            if winner_is_user:
                rp_change = self.calculate_rp_change(old_rp, avg_level * 100, True)  # Bot strength based on level
                coin_reward = old_rank_data['coin_bonus']
                
                player['rank_points'] = max(0, old_rp + rp_change)
                player['coins'] += coin_reward
                
                new_rank, new_rank_data = self.get_player_rank(player['rank_points'])
                
                final_embed.title = "🏆 Victory! 🏆"
                final_embed.description = f"You defeated the AI!\n"
                final_embed.description += f"**Coins:** +{coin_reward} 💰\n"
                final_embed.description += f"**Rank Points:** +{rp_change} RP 📈\n"
                final_embed.description += f"**Rank:** {old_rank} → {new_rank}"
                
                if new_rank != old_rank:
                    final_embed.description += f"\n🎉 **RANK UP!** Welcome to {new_rank}!"
                    final_embed.color = discord.Color.from_str(f"#{new_rank_data['color']}")
            else:
                rp_change = self.calculate_rp_change(old_rp, avg_level * 100, False)
                coin_loss = 20
                
                player['rank_points'] = max(0, old_rp + rp_change)  # rp_change is negative
                player['coins'] = max(0, player['coins'] - coin_loss)
                
                new_rank, new_rank_data = self.get_player_rank(player['rank_points'])
                
                final_embed.title = "☠️ Defeat ☠️"
                final_embed.description = f"The AI was victorious.\n"
                final_embed.description += f"**Coins:** -{coin_loss} 💸\n"
                final_embed.description += f"**Rank Points:** {rp_change} RP 📉\n"
                final_embed.description += f"**Rank:** {old_rank} → {new_rank}"
                
                if new_rank != old_rank:
                    final_embed.description += f"\n😞 **RANK DOWN** to {new_rank}"
                    final_embed.color = discord.Color.from_str(f"#{new_rank_data['color']}")
            
            db.update_player(user.id, player)
            final_embed.set_footer(text=f"Balance: {player['coins']} coins | RP: {player['rank_points']} ({new_rank})")
            await battle_message.edit(embed=final_embed, view=None)
        
        except Exception as e:
            print(f"An error occurred during AI battle: {e}")
            await ctx.send("An unexpected error occurred during the battle. The match has been concluded.")
        
        finally:
            self.active_battles.remove(user.id)

    def _create_hp_bar(self, current, max_val, length=12):
        if max_val <= 0: return f"`{'░' * length}` 0%"
        percent = max(0, min(1, current / max_val))
        filled_length = int(length * percent)
        
        # Better visibility for both dark and light themes
        if percent > 0.7:
            bar_char = '█'  # Full block - green zone
            color_indicator = '🟢'
        elif percent > 0.3:
            bar_char = '▓'  # Dark shade - yellow zone  
            color_indicator = '🟡'
        else:
            bar_char = '▒'  # Medium shade - red zone
            color_indicator = '🔴'
            
        empty_char = '░'  # Light shade for empty
        bar = bar_char * filled_length + empty_char * (length - filled_length)
        percentage = int(percent * 100)
        return f"{color_indicator}`{bar}` {percentage}%"

    def _create_battle_embed(self, log, t1, t2, p1_user, p2_user, p1_active, p2_active, footer_text=None):
        embed = discord.Embed(title=f"⚔️ {p1_user.display_name} vs {p2_user.display_name}", color=discord.Color.red())
        
        # Active fighters section with enhanced HP bars
        if p1_active and p2_active:
            p1_hp_bar = self._create_hp_bar(p1_active['current_hp'], p1_active['stats']['HP'], 12)
            p2_hp_bar = self._create_hp_bar(p2_active['current_hp'], p2_active['stats']['HP'], 12)
            
            active_display = f"🥊 **{p1_active['name']}** (Lv.{p1_active['level']})\n{p1_hp_bar}\n"
            active_display += f"⚡ ATK: {p1_active['stats']['ATK']} | DEF: {p1_active['stats']['DEF']} | SPD: {p1_active['stats']['SPD']}\n\n"
            active_display += f"🤖 **{p2_active['name']}** (Lv.{p2_active['level']}) [AI]\n{p2_hp_bar}\n"
            active_display += f"⚡ ATK: {p2_active['stats']['ATK']} | DEF: {p2_active['stats']['DEF']} | SPD: {p2_active['stats']['SPD']}"
            
            embed.add_field(name="🔥 Active Fighters", value=active_display, inline=False)
        
        # Team status (more compact)
        for user, team, active_char in [(p1_user, t1, p1_active), (p2_user, t2, p2_active)]:
            team_status = []
            for i, c in enumerate(team, 1):
                active_indicator = "🟢" if c is active_char and c['current_hp'] > 0 else "⚪"
                status = "💀" if c['current_hp'] <= 0 else f"{round(c['current_hp'])}/{c['stats']['HP']}"
                team_status.append(f"{active_indicator} **{c['name']}** `{status}`")
            
            team_name = f"🛡️ {user.display_name}'s Team" if user != self.bot.user else "🤖 AI Team"
            embed.add_field(name=team_name, value="\n".join(team_status) or "Defeated", inline=True)
            
        # Enhanced battle log - keep more history and format better
        if log:
            formatted_log = []
            for entry in log[-10:]:  # Keep last 10 entries instead of 5
                if "uses" in entry and "on" in entry:
                    formatted_log.append(f"⚔️ {entry}")
                elif "damage" in entry and "hits" in entry:
                    formatted_log.append(f"💥 {entry}")
                elif "defeated" in entry or "fainted" in entry:
                    formatted_log.append(f"💀 {entry}")
                elif "sends out" in entry:
                    formatted_log.append(f"🔄 {entry}")
                elif "missed" in entry:
                    formatted_log.append(f"💨 {entry}")
                elif "CRITICAL" in entry:
                    formatted_log.append(f"💯 {entry}")
                elif "New Round" in entry:
                    formatted_log.append(f"🔄 ═══ {entry} ═══")
                else:
                    formatted_log.append(f"📢 {entry}")
            
            # Ensure we don't exceed Discord's field limit
            log_text = "\n".join(formatted_log)
            if len(log_text) > 1000:
                # Trim from the beginning if too long
                log_text = "..." + log_text[-950:]
            
            embed.add_field(name="📜 Battle History", value=f"```{log_text}```", inline=False)
        
        if footer_text:
            embed.set_footer(text=footer_text)
        return embed

async def setup(bot):
    await bot.add_cog(BattleAI(bot))

def get_player_rank(self, rank_points):
        """Returns the player's current rank tier based on rank points."""
        for rank_name, rank_data in self.ranks['tiers'].items():
            if rank_data['min_rp'] <= rank_points <= rank_data['max_rp']:
                return rank_name, rank_data
        return "Bronze", self.ranks['tiers']['Bronze']  # Default fallback

    def calculate_rp_change(self, winner_rp, loser_rp, won):
        """Calculates rank point changes based on current ranks and outcome."""
        winner_rank, winner_data = self.get_player_rank(winner_rp)
        loser_rank, loser_data = self.get_player_rank(loser_rp)
        
        if won:
            base_rp = winner_data['win_rp']
            # Reduce RP gain if fighting lower ranked opponents
            if winner_rp > loser_rp + 500:
                base_rp = max(5, base_rp - 5)
            return base_rp
        else:
            base_rp = winner_data['loss_rp']
            # Reduce RP loss if fighting higher ranked opponents
            if loser_rp > winner_rp + 500:
                base_rp = max(-5, base_rp + 5)
            return base_rp
