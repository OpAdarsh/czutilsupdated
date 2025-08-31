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

    
        

async def setup(bot):
    await bot.add_cog(Utils(bot))
