import discord
from discord.ext import commands
import os
import random
import hashlib
import asyncio
import re
# Import the database functions to manage player coins
import database as db

# AFK storage dictionary (can remain in memory as it's not critical)
AFK_USERS = {}

class Utils(commands.Cog):
    """A cog for general utility commands like afk and fun commands."""
    def __init__(self, bot):
        self.bot = bot
        # self.ship_cache = {}  <-- Removed as the ship command is no longer needed.

    @commands.command(name='afk', help="!afk [message] - Sets your AFK status.")
    async def afk_command(self, ctx, *, message="I'm AFK right now."):
        AFK_USERS[ctx.author.id] = {"message": message}
        await ctx.send(f"💤 **{ctx.author.display_name}** is now AFK. Reason: *{message}*")

    @commands.command(name='calculator', aliases=['calc'], help="!calc <expression> - A simple calculator.")
    async def calculator(self, ctx, *, expression: str):
        # Securely evaluate the expression
        # Only allow digits, basic operators, parentheses, and spaces
        if not re.match(r"^[0-9\s()+\-*/.]*$", expression):
            await ctx.send("Invalid characters in expression. Only numbers and `+ - * / ()` are allowed.")
            return
        try:
            # Safe evaluation
            result = eval(expression, {"__builtins__": {}}, {})
            await ctx.send(f"🧮 Result: `{expression} = {result}`")
        except (SyntaxError, ZeroDivisionError, TypeError, OverflowError) as e:
            await ctx.send(f"Invalid mathematical expression: `{e}`")

    @commands.command(name='slots', help="!slots <bet> - Play the slot machine!")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slots(self, ctx, bet: int):
        """A weighted slot machine game with a cleaner UI."""
        player = db.get_player(ctx.author.id)
        
        if bet <= 0:
            await ctx.send("You must bet a positive amount of coins."); return
        if player['coins'] < bet:
            await ctx.send("You don't have enough coins to make that bet."); return

        player['coins'] -= bet
        
        reels = {'🍒': 25, '💰': 20, '🔔': 15, '💎': 5}
        
        spinning_embed = discord.Embed(title="🎰 Slot Machine 🎰", description="Spinning the reels...", color=discord.Color.blue())
        spinning_embed.add_field(name="Bet", value=f"{bet} coins")
        msg = await ctx.send(embed=spinning_embed)
        await asyncio.sleep(2)

        result_reels = random.choices(list(reels.keys()), weights=list(reels.values()), k=3)
        
        winnings = 0
        result_text = ""
        win_color = discord.Color.red()
        
        if result_reels.count('💎') == 3:
            winnings = bet * 10
            result_text = f"💎💎💎 **JACKPOT!** You win **{winnings}** coins! 💎💎💎"
            win_color = discord.Color.gold()
        elif result_reels.count('🍒') == 3:
            winnings = bet * 5
            result_text = f"🍒🍒🍒 **BIG WIN!** You get **{winnings}** coins! 🍒🍒🍒"
            win_color = discord.Color.green()
        elif result_reels.count('💰') == 3:
            winnings = bet * 2
            result_text = f"💰💰💰 **You doubled up!** You win **{winnings}** coins! 💰💰💰"
            win_color = discord.Color.green()
        elif result_reels.count('🔔') == 3:
            winnings = bet
            result_text = f"🔔🔔🔔 **Bet back!** You get **{winnings}** coins! 🔔🔔🔔"
            win_color = discord.Color.light_grey()
        else:
            result_text = "Sorry, you lost this time. Better luck next time!"
            
        player['coins'] += winnings
        db.update_player(ctx.author.id, player)

        final_embed = discord.Embed(title="🎰 Slot Machine 🎰", description=result_text, color=win_color)
        final_embed.add_field(
            name="Result", 
            value=f"**` {result_reels[0]} | {result_reels[1]} | {result_reels[2]} `**", 
            inline=False
        )
        final_embed.set_footer(text=f"Your new balance: {player['coins']} coins")
        await msg.edit(embed=final_embed)

    @slots.error
    async def slots_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify an amount to bet. Usage: `!slots <amount>`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Please enter a valid number for your bet.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"The slot machine is cooling down! Try again in {error.retry_after:.1f} seconds.", delete_after=5)

async def setup(bot):
    await bot.add_cog(Utils(bot))
