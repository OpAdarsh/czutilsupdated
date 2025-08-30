import discord
from discord.ext import commands
import json
import os
import random
import asyncio
# Import the database functions
import database as db

class Admin(commands.Cog):
    """A cog for bot administration commands, restricted to the Bot Admin."""
    def __init__(self, bot):
        self.bot = bot

    # This check runs before any command in this cog is executed.
    async def cog_check(self, ctx):
        admin_id_str = self.bot.config.get('ADMIN_ID')
        if not admin_id_str:
            raise commands.CheckFailure("The `ADMIN_ID` is not set in your config file.")
        try:
            admin_id = int(admin_id_str)
            if ctx.author.id != admin_id:
                raise commands.CheckFailure("You are not authorized to use this command.")
            return True
        except (ValueError, TypeError):
            raise commands.CheckFailure("The `ADMIN_ID` in your config file is not a valid user ID.")

    # This handles permission errors for all commands in this cog.
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"❌ **Permission Denied:** {error}")

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
    async def load_cog(self, ctx, cog_name: str):
        try:
            await self.bot.load_extension(f'cogs.{cog_name}')
            await ctx.send(f"✅ Successfully loaded cog `{cog_name}`.")
        except Exception as e:
            await ctx.send(f"An error occurred: `{e}`")

    @commands.command(name='unload', help="!unload <cog_name> - Unloads a cog.")
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
    async def reload_cog(self, ctx, cog_name: str):
        try:
            await self.bot.reload_extension(f'cogs.{cog_name}')
            await ctx.send(f"✅ Successfully reloaded cog `{cog_name}`.")
        except Exception as e:
            await ctx.send(f"An error occurred: `{e}`")

    @commands.command(name='reboot', help="!reboot - Reboots the bot.")
    async def reboot(self, ctx):
        await ctx.send("Rebooting...")
        await self.bot.close()

    @commands.command(name='addbalance', aliases=['addbal'], help="!addbal <member> <amount> - Adds coins to a user.")
    async def add_balance(self, ctx, member: discord.Member, amount: int):
        player = db.get_player(member.id)
        player['coins'] += amount
        db.update_player(member.id, player)
        await ctx.send(f"✅ Added **{amount}** coins to {member.mention}. Their new balance is **{player['coins']}**.")
        
    @commands.command(name='addchar', help="!addchar <member> <name> - Gives a character to a user.")
    async def add_character(self, ctx, member: discord.Member, *, character_name: str):
        stats_cog = self.bot.get_cog('Stat Calculations')
        cz_cog = self.bot.get_cog('Core Gameplay')
        if not stats_cog or not cz_cog:
            await ctx.send("❌ **Error:** Core cogs are not loaded.")
            return
            
        found_char_name = next((name for name in cz_cog.characters if name.lower() == character_name.lower()), None)
        if not found_char_name:
            await ctx.send(f"❌ **Error:** Character '{character_name}' not found in the game data.")
            return
            
        player = db.get_player(member.id)
        base_char_data = cz_cog.characters[found_char_name]
        new_char_instance = cz_cog._create_character_instance(base_char_data)
        for stat in new_char_instance['individual_ivs'].keys():
            new_char_instance['individual_ivs'][stat] = 31
        new_char_instance['iv'] = 100.0
        new_char_instance['stats'] = stats_cog._calculate_stats(base_char_data, new_char_instance['individual_ivs'], 1)
        char_id = player['next_character_id']
        player['characters'][char_id] = new_char_instance
        player['next_character_id'] += 1
        db.update_player(member.id, player)
        await ctx.send(f"✅ Gave a **100% IV {found_char_name}** (ID: {char_id}) to {member.mention}.")

    @commands.command(name='datatransfer', aliases=['dt'], help="!dt <from> <to> - Transfers all RPG data.")
    async def data_transfer(self, ctx, source_member: discord.Member, target_member: discord.Member):
        if source_member.id == target_member.id:
            await ctx.send("❌ You cannot transfer data to the same user."); return
        source_player = db.get_player(source_member.id)
        target_player = db.get_player(target_member.id)
        target_player['coins'] += source_player.get('coins', 0)
        for item, count in source_player.get('inventory', {}).items():
            target_player['inventory'][item] = target_player['inventory'].get(item, 0) + count
        next_id = target_player.get('next_character_id', 1)
        for char_data in source_player.get('characters', {}).values():
            target_player['characters'][next_id] = char_data
            next_id += 1
        target_player['next_character_id'] = next_id
        db.reset_player(source_member.id)
        db.update_player(target_member.id, target_player)
        await ctx.send(f"✅ **Transfer Complete!** Data from {source_member.mention} has been moved to {target_member.mention}.")

    @commands.command(name='maxlevel', help="!maxlevel <member> <char_id> - Maxes a character's level.")
    async def max_level_character(self, ctx, member: discord.Member, char_id: int):
        player = db.get_player(member.id)
        if char_id not in player.get('characters', {}):
            await ctx.send(f"❌ User {member.display_name} does not own a character with ID `{char_id}`."); return
        character = player['characters'][char_id]
        if character.get('level', 1) >= 100:
            await ctx.send(f"✅ **{character['name']}** is already at max level."); return
        stats_cog = self.bot.get_cog('Stat Calculations')
        if not stats_cog:
            await ctx.send("Stat calculation cog not loaded."); return
        base_char_data = self.bot.get_cog('Core Gameplay').characters.get(character['name'])
        if not base_char_data:
            await ctx.send("Could not find base character data."); return
        character['level'] = 100
        character['xp'] = 0
        character['stats'] = stats_cog._calculate_stats(base_char_data, character['individual_ivs'], 100)
        db.update_player(member.id, player)
        await ctx.send(f"🎉 **Success!** {member.mention}'s **{character['name']}** (ID: {char_id}) has been maxed out to Level 100.")
    
    @commands.command(name='resetplayersdata', aliases=['rpd'], help="!rpd - Wipes all player data.")
    async def reset_players_data(self, ctx):
        await ctx.send(
            "**⚠️ WARNING: This is a destructive action and will wipe ALL player data permanently.**\n"
            "To confirm, type `CONFIRM` in the next 20 seconds."
        )
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() == "CONFIRM"
        try:
            await self.bot.wait_for('message', timeout=20.0, check=check)
            await ctx.send("Confirmation received. Wiping data...")
            db.reset_all_players()
            await ctx.send("✅ **All player data has been successfully wiped.**")
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. Player data reset has been cancelled.")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while wiping data: `{e}`")
            
    @commands.command(name='clearuserdata', help="!clearuserdata <member> - Clears all data for a user.", category="Admin")
    async def clearuserdata(self, ctx, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.send("You cannot clear your own data this way.")
            return
        await ctx.send(
            f"**⚠️ WARNING: This is a destructive action and will wipe ALL player data for {member.mention} permanently.**\n"
            "To confirm, type `CONFIRM` in the next 20 seconds."
        )
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() == "CONFIRM"
        try:
            await self.bot.wait_for('message', timeout=20.0, check=check)
            await ctx.send(f"Confirmation received. Wiping data for {member.display_name}...")
            db.reset_player(member.id)
            await ctx.send(f"✅ **All data for {member.display_name} has been successfully wiped.**")
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. Player data wipe has been cancelled.")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while wiping data: `{e}`")

async def setup(bot):
    await bot.add_cog(Admin(bot))

