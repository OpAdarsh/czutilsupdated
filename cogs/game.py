# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import random
import json
from collections import defaultdict, Counter
import os
import asyncio
import time

# Dictionary to store ongoing games, using the channel ID as the key
active_games = {}
LEADERBOARD_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'leaderboard.json')

class Game(commands.Cog):
    """A cog for a word-guessing game."""
    def __init__(self, bot):
        self.bot = bot
        self.words_by_length = self._load_words()
        self.new_game_prompts = {} # Stores messages asking to start a new game
        self.hint_confirms = {} # Stores messages for hint confirmations
        self.hint_cooldowns = {} # Manually track hint cooldowns

    def _load_words(self):
        """Loads words from the data/words.json file and prepares them for the game."""
        try:
            path = os.path.join(os.path.dirname(__file__), '..', 'data', 'words.json')
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                processed_data = {}
                all_words = set()
                
                for key, words in data.items():
                    length_str = key.split('_')[0]
                    if length_str.isdigit():
                        word_set = {word.upper() for word in words}
                        processed_data[length_str] = word_set
                        if int(length_str) in [3, 4, 5, 6]:
                            all_words.update(word_set)

                processed_data["all_words"] = all_words
                if "7" not in processed_data:
                     processed_data["7"] = {"EXAMPLE", "LETTERS", "CHANNEL", "MESSAGE", "COMMAND"}
                return processed_data

        except (FileNotFoundError, json.JSONDecodeError):
            print("Error: words.json not found or is improperly formatted.")
            return {"3": set(), "4": set(), "5": set(), "6": set(), "7": {"EXAMPLE"}, "all_words": set()}

    def _load_leaderboard(self):
        """Loads the leaderboard from a JSON file."""
        if not os.path.exists(LEADERBOARD_FILE):
            return {}
        try:
            with open(LEADERBOARD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save_leaderboard(self, leaderboard_data):
        """Saves the leaderboard to a JSON file."""
        with open(LEADERBOARD_FILE, 'w', encoding='utf-8') as f:
            json.dump(leaderboard_data, f, indent=4)

    async def _send_temp_scoreboard(self, channel, game_state):
        """Creates and sends a temporary scoreboard message."""
        scoreboard_text = "### 🏆 Current Scoreboard\n"
        sorted_scores = sorted(game_state["scores"].items(), key=lambda item: item[1], reverse=True)

        if not sorted_scores:
            scoreboard_text += "*No one has scored yet!*"
        else:
            for user_id, score in sorted_scores:
                member = channel.guild.get_member(user_id)
                if member:
                    scoreboard_text += f"**{member.display_name}**: {score} points\n"
        
        await channel.send(scoreboard_text, delete_after=5)

    async def _letter_reminder_task(self, ctx, game_state):
        """A background task that resends the game letters periodically."""
        while ctx.channel.id in active_games:
            await asyncio.sleep(60) 
            if ctx.channel.id not in active_games:
                break 
            
            intro_embed = discord.Embed(
                title="Letters Reminder!",
                description=f"Find all the words you can (3-6 letters long) using these letters!\nThere are **{len(game_state['possible_words'])}** words to find.",
                color=discord.Color.blue()
            )
            intro_embed.add_field(name="Letters", value=" ".join(f"`{l}`" for l in game_state['letters']), inline=False)
            await ctx.send(embed=intro_embed, delete_after=20)


    @commands.command(name='startgame', help="!startgame")
    async def start_game(self, ctx):
        """Starts a new word game in the channel."""
        if ctx.channel.id in active_games:
            await ctx.send("A game is already in progress in this channel!")
            return

        source_words = self.words_by_length.get("7")
        if not source_words:
            await ctx.send("Could not find suitable words to generate the game.")
            return

        secret_word = random.choice(list(source_words))
        letters = list(secret_word)
        random.shuffle(letters)
        letter_counts = Counter(letters)

        possible_words = {
            word for word in self.words_by_length["all_words"]
            if all(letter_counts[char] >= count for char, count in Counter(word).items())
        }

        game_state = {
            "letters": letters,
            "letter_counts": letter_counts,
            "scores": defaultdict(int),
            "found_words": set(),
            "possible_words": possible_words,
            "current_hint": None,
            "reminder_task": None,
            "intro_message": None
        }
        active_games[ctx.channel.id] = game_state
        
        intro_embed = discord.Embed(
            title="Word Game Started!",
            description=f"Find all the words you can (3-6 letters long) using these letters!\nThere are **{len(possible_words)}** words to find.",
            color=discord.Color.blue()
        )
        intro_embed.add_field(name="Letters", value=" ".join(f"`{l}`" for l in letters), inline=False)
        
        intro_message = await ctx.send(embed=intro_embed)
        game_state["intro_message"] = intro_message
        
        task = self.bot.loop.create_task(self._letter_reminder_task(ctx, game_state))
        game_state["reminder_task"] = task


    async def _end_game_flow(self, ctx):
        """Handles the logic for ending a game and prompting for a new one."""
        if ctx.channel.id not in active_games:
            return

        game_state = active_games.pop(ctx.channel.id)
        
        if game_state.get("reminder_task"):
            game_state["reminder_task"].cancel()

        final_scores = game_state["scores"]
        
        # --- Update Leaderboard ---
        leaderboard = self._load_leaderboard()
        for user_id, score in final_scores.items():
            leaderboard[str(user_id)] = leaderboard.get(str(user_id), 0) + score
        self._save_leaderboard(leaderboard)
        # --- End Leaderboard Update ---
        
        embed = discord.Embed(title="🏁 Game Over!", color=discord.Color.gold())
        
        if not final_scores:
            embed.description = "The game has ended! No one scored."
        else:
            sorted_scores = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
            winner_id, winner_score = sorted_scores[0]
            winner = ctx.guild.get_member(winner_id)
            embed.description = f"**🏆 Winner: {winner.mention} with {winner_score} points!**"
            score_text = "\n".join(
                f"{ctx.guild.get_member(uid).mention}: {s} points" 
                for uid, s in sorted_scores if ctx.guild.get_member(uid)
            )
            embed.add_field(name="Final Scores", value=score_text, inline=False)

        found_count = len(game_state["found_words"])
        total_count = len(game_state["possible_words"])
        remaining_count = total_count - found_count

        embed.add_field(
            name="Game Summary",
            value=f"You found **{found_count}** out of **{total_count}** possible words.\nThere were **{remaining_count}** words left.",
            inline=False
        )
        
        await ctx.send(embed=embed)

        prompt_message = await ctx.send("Play again?")
        await prompt_message.add_reaction("✅")
        await prompt_message.add_reaction("❌")
        self.new_game_prompts[prompt_message.id] = ctx

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listens for messages to handle prefix-less guesses during a game."""
        if message.author.bot or not message.guild:
            return

        game_state = active_games.get(message.channel.id)
        if not game_state:
            return

        content = message.content.strip()
        if ' ' in content or not content.isalpha():
            return

        guess = content.upper()

        if guess in game_state["possible_words"]:
            if guess not in game_state["found_words"]:
                game_state["scores"][message.author.id] += 1
                game_state["found_words"].add(guess)
                await message.add_reaction("✅")
                
                if guess == game_state.get("current_hint"):
                    game_state["current_hint"] = None

                await self._send_temp_scoreboard(message.channel, game_state)

                remaining_words = len(game_state["possible_words"]) - len(game_state["found_words"])
                if remaining_words > 0:
                    await message.channel.send(f"**{remaining_words}** words left to find!", delete_after=5)
                else:
                    await message.channel.send("🎉 You've found all the words! Ending game...", delete_after=5)
                    ctx = await self.bot.get_context(message)
                    await self._end_game_flow(ctx)
            else:
                await message.add_reaction("🤔")
    
    @commands.command(name='hint', help="!hint")
    async def get_hint(self, ctx):
        """Provides a hint for an unfound word."""
        game_state = active_games.get(ctx.channel.id)
        if not game_state:
            return

        if game_state.get("current_hint"):
            if game_state["scores"][ctx.author.id] < 1:
                await ctx.send("You don't have enough points to buy a hint!", delete_after=10)
                return

            prompt_msg = await ctx.send("A hint is already active. Spend 1 point to see it again?")
            await prompt_msg.add_reaction("✅")
            await prompt_msg.add_reaction("❌")
            self.hint_confirms[prompt_msg.id] = ctx
            return

        cooldown_time = 90
        last_used = self.hint_cooldowns.get(ctx.author.id, 0)
        if time.time() - last_used < cooldown_time:
            await ctx.send(f"You can use the hint command again in **{cooldown_time - (time.time() - last_used):.0f}** seconds.", delete_after=5)
            return
        
        unfound_words = game_state["possible_words"] - game_state["found_words"]
        if not unfound_words:
            await ctx.send("All words have been found!", delete_after=10)
            return

        self.hint_cooldowns[ctx.author.id] = time.time() 
        hint_word = random.choice(list(unfound_words))
        game_state["current_hint"] = hint_word
        
        hint_list = ['_'] * len(hint_word)
        reveal_index = random.randint(0, len(hint_word) - 1)
        game_state["hint_index"] = reveal_index 
        hint_list[reveal_index] = hint_word[reveal_index]
        hint_display = "".join(f"`{c}`" for c in hint_list)
        
        await ctx.send(f"Here's a hint: {hint_display}", delete_after=15)
        await ctx.message.delete()

    @commands.command(name='shuffle', aliases=['sf'], help="!shuffle or !sf")
    async def shuffle_letters(self, ctx):
        """Shuffles the letters for the current game."""
        game_state = active_games.get(ctx.channel.id)
        if not game_state:
            return
        
        random.shuffle(game_state["letters"])
        
        intro_embed = discord.Embed(
            title="Letters Shuffled!",
            description=f"Find all the words you can (3-6 letters long) using these letters!\nThere are **{len(game_state['possible_words'])}** words to find.",
            color=discord.Color.blue()
        )
        intro_embed.add_field(name="Letters", value=" ".join(f"`{l}`" for l in game_state['letters']), inline=False)
        
        # Delete old intro message and send a new one
        if game_state.get("intro_message"):
            try:
                await game_state["intro_message"].delete()
            except discord.NotFound:
                pass # Ignore if message was already deleted
        
        new_intro = await ctx.send(embed=intro_embed)
        game_state["intro_message"] = new_intro
        await ctx.message.delete()

    @commands.command(name='leaderboard', aliases=['lb'], help="!leaderboard or !lb")
    async def leaderboard(self, ctx):
        """Displays the server's word game leaderboard."""
        leaderboard_data = self._load_leaderboard()
        if not leaderboard_data:
            await ctx.send("The leaderboard is empty!")
            return

        sorted_board = sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True)
        
        embed = discord.Embed(title="🏆 Word Game Leaderboard", color=discord.Color.gold())
        
        lines = []
        for i, (user_id, score) in enumerate(sorted_board[:10], 1):
            user = await self.bot.fetch_user(int(user_id))
            lines.append(f"**{i}.** {user.mention} - `{score}` points")
        
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


    @commands.command(name='endgame', aliases=['stop'], help="!endgame or !stop")
    async def end_game(self, ctx):
        """Ends the current word game in the channel. (Moderator only)"""
        config = self.bot.config
        mod_role_id_1 = config.get('MOD_ROLE_ID_1')
        mod_role_id_2 = config.get('MOD_ROLE_ID_2')
        
        author_roles = [role.id for role in ctx.author.roles]
        is_mod = (mod_role_id_1 in author_roles) or (mod_role_id_2 in author_roles)

        if not is_mod and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You don't have permission to end the game.", delete_after=10)
            return

        if ctx.channel.id not in active_games:
            await ctx.send("No game is currently in progress.")
            return
        
        await self._end_game_flow(ctx)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handles reactions for prompts."""
        if user.bot:
            return

        if reaction.message.id in self.new_game_prompts:
            ctx = self.new_game_prompts.pop(reaction.message.id)
            await reaction.message.delete()

            if str(reaction.emoji) == '✅':
                await self.start_game(ctx)
            elif str(reaction.emoji) == '❌':
                await ctx.send("Okay, no new game.", delete_after=10)
            return

        if reaction.message.id in self.hint_confirms:
            ctx = self.hint_confirms.pop(reaction.message.id)
            
            if user.id != ctx.author.id:
                return

            await reaction.message.delete()
            
            if str(reaction.emoji) == '✅':
                game_state = active_games.get(ctx.channel.id)
                if game_state and game_state["scores"][user.id] > 0:
                    game_state["scores"][user.id] -= 1
                    
                    hint_word = game_state["current_hint"]
                    hint_list = ['_'] * len(hint_word)
                    reveal_index = game_state["hint_index"]
                    hint_list[reveal_index] = hint_word[reveal_index]
                    hint_display = "".join(f"`{c}`" for c in hint_list)
                    
                    await ctx.send(f"Hint purchased! The hint is still: {hint_display}", delete_after=15)
                    await self._send_temp_scoreboard(ctx.channel, game_state)
                else:
                    await ctx.send("You no longer have enough points.", delete_after=10)
            elif str(reaction.emoji) == '❌':
                await ctx.send("Hint purchase cancelled.", delete_after=10)


async def setup(bot):
    await bot.add_cog(Game(bot))
