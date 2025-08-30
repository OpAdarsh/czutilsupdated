import discord
from discord.ext import commands
import json
import os
import random
import asyncio
# Import the database functions
import database as db

# --- Custom Permission Check for Bot Admin ---
def is_bot_admin():
    """A check to see if the command author is the bot admin specified in the config."""
    async def predicate(ctx):
        admin_id = ctx.bot.config.get('ADMIN_ID')
        try:
            return ctx.author.id == int(admin_id)
        except (ValueError, TypeError):
            return False
    return commands.check(predicate)

class Admin(commands.Cog):
    """A cog for bot administration commands, restricted to the Bot Admin."""
    def __init__(self, bot):
        self.bot = bot

    def get_admin_help_embed(self):
        """Generates the embed for the private admin help command."""
        embed = discord.Embed(
            title="👑 Admin Commands",
            description="Here are all the commands available to the bot administrator:",
            color=discord.Color.gold()
        )
        for command in self.get_commands():
            aliases = f"| {', '.join(command.aliases)}" if command.aliases else ""
            help_text = command.help.split('-')[1].strip() if '-' in command.help else command.help
            embed.add_field(
                name=f"`{self.bot.config.get('PREFIX', '!')}{command.name} {aliases}`",
                value=help_text,
                inline=False
            )
        return embed

    @commands.command(name='load', help="!load <cog_name> - Loads a cog.")
    @is_bot_admin()
    async def load_cog(self, ctx, cog_name: str):
        try:
            await self.bot.load_extension(f'cogs.{cog_name}')
            await ctx.send(f"✅ Successfully loaded cog `{cog_name}`.")
        except Exception as e:
            await ctx.send(f"An error occurred: `{e}`")

    @commands.command(name='unload', help="!unload <cog_name> - Unloads a cog.")
    @is_bot_admin()
    async def unload_cog(self, ctx, cog_name: str):
        if cog_name.lower() == "admin":
            await ctx.send("❌ I cannot unload the admin cog.")
            return
        try:
            await self.bot.unload_extension(f'cogs.{cog_name}')
            await ctx.send(f"✅ Successfully unloaded cog `{cog_name}`.")
        except Exception as e:
            await ctx.send(f"An error occurred: `{e}`")

    @commands.command(name='reload', help="!reload <cog_name> - Reloads a cog.")
    @is_bot_admin()
    async def reload_cog(self, ctx, cog_name: str):
        try:
            await self.bot.reload_extension(f'cogs.{cog_name}')
            await ctx.send(f"✅ Successfully reloaded cog `{cog_name}`.")
        except Exception as e:
            await ctx.send(f"An error occurred: `{e}`")

    @commands.command(name='reboot', help="!reboot - Reboots the bot.")
    @is_bot_admin()
    async def reboot(self, ctx):
        await ctx.send("Rebooting...")
        await self.bot.close()

    @commands.command(name='addbalance', aliases=['addbal'], help="!addbal <member> <amount> - Adds coins to a user.")
    @is_bot_admin()
    async def add_balance(self, ctx, member: discord.Member, amount: int):
        player = db.get_player(member.id)
        player['coins'] += amount
        db.update_player(member.id, player)
        await ctx.send(f"✅ Added **{amount}** coins to {member.mention}. Their new balance is **{player['coins']}**.")
        
    @commands.command(name='addchar', help="!addchar <member> <name> - Gives a character to a user.")
    @is_bot_admin()
    async def add_character(self, ctx, member: discord.Member, *, character_name: str):
        """Gives a specific character with 100% IV to a user."""
        cz_cog = self.bot.get_cog('CZ')
        if not cz_cog or not cz_cog.characters:
            await ctx.send("❌ **Error:** The CZ cog or its character data is not loaded.")
            return
            
        # Find the character in the base data (case-insensitive)
        found_char_name = next((name for name in cz_cog.characters if name.lower() == character_name.lower()), None)
        
        if not found_char_name:
            await ctx.send(f"❌ **Error:** Character '{character_name}' not found in the game data.")
            return
            
        player = db.get_player(member.id)
        base_char_data = cz_cog.characters[found_char_name]
        base_char = {"name": found_char_name, **base_char_data}
        
        # Create a perfect IV instance with all stats at 31/31
        new_char_instance = cz_cog._create_character_instance(base_char, 0)  # IV parameter is ignored now
        
        # Set all individual IVs to maximum (31)
        for stat in new_char_instance['individual_ivs'].keys():
            new_char_instance['individual_ivs'][stat] = 31
            
        # Recalculate overall IV percentage (should be 100%)
        total_iv_points = sum(new_char_instance['individual_ivs'].values())
        max_possible_iv_points = 31 * len(new_char_instance['individual_ivs'])
        new_char_instance['iv'] = round((total_iv_points / max_possible_iv_points) * 100, 2)
        
        # Recalculate stats based on perfect IVs
        stats_dict = {k: v for k, v in base_char.items() if k not in ["Ability", "Description", "name", "id"]}
        for stat, base_value in stats_dict.items():
            iv_boost = base_value * (new_char_instance['individual_ivs'][stat]/31) * 0.3
            new_char_instance['stats'][stat] = max(1, round(base_value + iv_boost))
        
        char_id = player['next_character_id']
        player['characters'][char_id] = new_char_instance
        player['next_character_id'] += 1
        
        db.update_player(member.id, player)
        await ctx.send(f"✅ Gave a **100% IV {found_char_name}** (ID: {char_id}) to {member.mention}.")

    @commands.command(name='datatransfer', aliases=['dt'], help="!dt <from> <to> - Transfers all RPG data.")
    @is_bot_admin()
    async def data_transfer(self, ctx, source_member: discord.Member, target_member: discord.Member):
        if source_member.id == target_member.id:
            await ctx.send("❌ You cannot transfer data to the same user."); return

        source_player = db.get_player(source_member.id)
        target_player = db.get_player(target_member.id)

        target_player['coins'] += source_player.get('coins', 0)
        for item, count in source_player.get('inventory', {}).items():
            target_player['inventory'][item] += count

        next_id = target_player.get('next_character_id', 1)
        for char_data in source_player.get('characters', {}).values():
            target_player['characters'][next_id] = char_data
            next_id += 1
        target_player['next_character_id'] = next_id
        
        db.reset_player(source_member.id)
        db.update_player(target_member.id, target_player)
        
        await ctx.send(f"✅ **Transfer Complete!** Data from {source_member.mention} has been moved to {target_member.mention}.")

    @commands.command(name='maxlevel', help="!maxlevel <member> <char_id> - Maxes a character's level.")
    @is_bot_admin()
    async def max_level_character(self, ctx, member: discord.Member, char_id: int):
        player = db.get_player(member.id)
        if char_id not in player.get('characters', {}):
            await ctx.send(f"❌ User {member.display_name} does not own a character with ID `{char_id}`."); return

        character = player['characters'][char_id]
        if character.get('level', 1) >= 100:
            await ctx.send(f"✅ **{character['name']}** is already at max level."); return

        levels_to_gain = 100 - character.get('level', 1)
        stat_points_to_add = levels_to_gain * 3
        stat_keys = list(character['stats'].keys())
        if not stat_keys:
            await ctx.send("❌ Character has no stats to upgrade."); return
            
        for _ in range(stat_points_to_add):
            character['stats'][random.choice(stat_keys)] += 1
            
        character['level'] = 100
        character['xp'] = 0
        
        db.update_player(member.id, player)
        await ctx.send(f"🎉 **Success!** {member.mention}'s **{character['name']}** (ID: {char_id}) has been maxed out to Level 100.")
    
    @commands.command(name='resetplayersdata', aliases=['rpd'], help="!rpd - Wipes all player data.")
    @is_bot_admin()
    async def reset_players_data(self, ctx):
        await ctx.send(
            "**⚠️ WARNING: This is a destructive action and will wipe ALL player data permanently.**\n"
            "To confirm, type `CONFIRM` in the next 20 seconds."
        )
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRM"
        try:
            await self.bot.wait_for('message', timeout=20.0, check=check)
            db.reset_all_players()
            await ctx.send("✅ **All player data has been successfully wiped.**")
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. Player data reset has been cancelled.")
            
async def setup(bot):
    await bot.add_cog(Admin(bot))
