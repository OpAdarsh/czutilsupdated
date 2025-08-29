import discord
from discord.ext import commands
import os
import random
import hashlib
import asyncio
import re
from data.compliments import COMPLIMENTS
# Import the database functions to manage player coins
import database as db

# AFK storage dictionary (can remain in memory as it's not critical)
AFK_USERS = {}

class Utils(commands.Cog):
    """A cog for general utility commands like afk and fun commands."""
    def __init__(self, bot):
        self.bot = bot
        self.ship_cache = {}

    @commands.command(name='afk', help="!afk [message] - Sets your AFK status.")
    async def afk_command(self, ctx, *, message="I'm AFK right now."):
        AFK_USERS[ctx.author.id] = {"message": message}
        await ctx.send(f"💤 **{ctx.author.display_name}** is now AFK. Reason: *{message}*")

    def _generate_ship_percentage(self, user1_id: int, user2_id: int) -> int:
        key = f"{min(user1_id, user2_id)}-{max(user1_id, user2_id)}"
        if key in self.ship_cache:
            return self.ship_cache[key]
        hash_object = hashlib.md5(key.encode())
        percentage = int(hash_object.hexdigest(), 16) % 101
        self.ship_cache[key] = percentage
        return percentage

    def _get_ship_description(self, percentage: int) -> dict:
        for threshold, compliments_list in sorted(COMPLIMENTS.items(), reverse=True):
            if percentage >= threshold:
                return {"description": random.choice(compliments_list), "color": self._get_color(percentage)}
        return {"description": random.choice(COMPLIMENTS[0]), "color": 0x8B0000}

    def _get_color(self, percentage: int) -> int:
        if percentage >= 95: return 0xFF69B4
        if percentage >= 85: return 0xFF1493
        if percentage >= 75: return 0xFF6347
        if percentage >= 65: return 0xFFA500
        if percentage >= 55: return 0xFFD700
        if percentage >= 25: return 0x9370DB
        return 0x696969

    @commands.command(name='ship', help="!ship <member1> [member2] - Ships two members.")
    async def ship(self, ctx, member1: discord.Member, member2: discord.Member = None):
        if member2 is None:
            member2 = ctx.author
        if member1.id == member2.id:
            await ctx.send("You can't ship a user with themselves!")
            return

        percentage = self._generate_ship_percentage(member1.id, member2.id)
        ship_data = self._get_ship_description(percentage)

        embed = discord.Embed(
            title=f"{member1.display_name} ❤️ {member2.display_name}",
            description=f"**{percentage}% Compatible**\n\n{ship_data['description']}", 
            color=ship_data['color']
        )
        # Polished progress bar
        progress_bar_blocks = int(percentage / 10)
        progress_bar = f"{'❤️' * progress_bar_blocks}{'🖤' * (10 - progress_bar_blocks)}"
        embed.add_field(name="Love Meter", value=progress_bar, inline=False)
        embed.set_thumbnail(url=member1.avatar.url)
        await ctx.send(embed=embed)
        
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

