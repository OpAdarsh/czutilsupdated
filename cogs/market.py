# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import database as db
import re

class Market(commands.Cog, name="Market"):
    """Commands for the player-driven market."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='market', invoke_without_command=True, help="!market - Interact with the player market.", category="Market")
    async def market(self, ctx):
        await ctx.send_help(ctx.command)

    @market.command(name='add', help="!market add <char_id> <price> - List a character on the market.")
    async def market_add(self, ctx, char_id: int, price: int):
        if price <= 0:
            await ctx.send("The price must be greater than zero."); return

        player = db.get_player(ctx.author.id)
        if char_id not in player['characters']:
            await ctx.send("You do not own a character with that ID."); return
        
        if char_id in player.get('team', []):
            await ctx.send("You cannot list a character that is on your team."); return
        
        if char_id == player.get('selected_character_id'):
            await ctx.send("You cannot list your selected character."); return

        character_to_list = player['characters'].pop(char_id)
        listing_id = db.add_market_listing(ctx.author.id, price, character_to_list)
        db.update_player(ctx.author.id, player)

        await ctx.send(f"✅ You have listed **{character_to_list['name']}** (Lvl {character_to_list['level']}) on the market for **{price}** coins. Listing ID: **#{listing_id}**")

    @market.command(name='view', help="!market view [--filters] - View market listings.")
    async def market_view(self, ctx, *, filters: str = None):
        listings = db.get_all_market_listings()
        if not listings:
            await ctx.send("The market is currently empty."); return

        filtered_listings = []
        if filters:
            # Simple parser for filters like --atk > 30, --iv 85, --spd < 50
            filter_pattern = re.compile(r"--(\w+)\s*([<>=])?\s*(\d+\.?\d*)")
            parsed_filters = filter_pattern.findall(filters)

            for listing in listings:
                char = listing['character_data']
                matches_all = True
                for key, op, val in parsed_filters:
                    key = key.lower()
                    op = op or '=' # Default to exact match
                    val = float(val)
                    
                    stat_val = None
                    if key == 'iv':
                        stat_val = char['iv']
                    elif key.upper() in char['individual_ivs']:
                        stat_val = char['individual_ivs'][key.upper()]
                    
                    if stat_val is None:
                        matches_all = False; break

                    if not ((op == '>' and stat_val > val) or
                            (op == '<' and stat_val < val) or
                            (op == '=' and stat_val == val)):
                        matches_all = False; break
                
                if matches_all:
                    filtered_listings.append(listing)
            listings = filtered_listings
            if not listings:
                await ctx.send("No listings match your filters."); return

        # Pagination for market view
        paginator = commands.Paginator(prefix='', suffix='', max_size=1024)
        for listing in listings:
            char = listing['character_data']
            try:
                seller = await self.bot.fetch_user(listing['seller_id'])
                seller_name = seller.display_name
            except discord.NotFound:
                seller_name = "Unknown User"
                
            paginator.add_line(
                f"**ID: #{listing['listing_id']}** | **{char['name']}** Lvl {char['level']} ({char['iv']}% IV)\n"
                f"Price: `{listing['price']}` coins | Seller: `{seller_name}`"
            )

        if not paginator.pages:
            await ctx.send("The market is empty or no listings matched your criteria."); return

        for page in paginator.pages:
            embed = discord.Embed(title="Player Market", description=page, color=discord.Color.blue())
            await ctx.send(embed=embed)
            
    @market.command(name='buy', help="!market buy <listing_id> - Purchase a character.")
    async def market_buy(self, ctx, listing_id: int):
        listing = db.get_market_listing(listing_id)
        if not listing:
            await ctx.send("This listing does not exist."); return
            
        if listing['seller_id'] == ctx.author.id:
            await ctx.send("You cannot buy your own listing."); return

        buyer = db.get_player(ctx.author.id)
        if buyer['coins'] < listing['price']:
            await ctx.send(f"You do not have enough coins. You need {listing['price']} coins."); return

        # Perform transaction
        seller = db.get_player(listing['seller_id'])
        
        buyer['coins'] -= listing['price']
        seller['coins'] += listing['price']
        
        char_data = listing['character_data']
        new_id = buyer['next_character_id']
        buyer['characters'][new_id] = char_data
        buyer['next_character_id'] += 1
        
        db.remove_market_listing(listing_id)
        db.update_player(buyer['user_id'], buyer)
        db.update_player(seller['user_id'], seller)
        
        await ctx.send(f"🎉 You have successfully purchased **{char_data['name']}** for **{listing['price']}** coins!")
        try:
            seller_user = await self.bot.fetch_user(seller['user_id'])
            await seller_user.send(f"Your listing for **{char_data['name']}** has sold for **{listing['price']}** coins!")
        except discord.HTTPException:
            pass # Can't DM user
            
    @market.command(name='remove', help="!market remove <listing_id> - Remove your market listing.")
    async def market_remove(self, ctx, listing_id: int):
        listing = db.get_market_listing(listing_id)
        if not listing:
            await ctx.send("This listing does not exist."); return
            
        if listing['seller_id'] != ctx.author.id:
            await ctx.send("You can only remove your own listings."); return
            
        player = db.get_player(ctx.author.id)
        char_data = listing['character_data']
        new_id = player['next_character_id']
        player['characters'][new_id] = char_data
        player['next_character_id'] += 1
        
        db.remove_market_listing(listing_id)
        db.update_player(ctx.author.id, player)
        
        await ctx.send(f"✅ You have removed your listing for **{char_data['name']}** from the market. It has been returned to your collection with the new ID #{new_id}.")

async def setup(bot):
    await bot.add_cog(Market(bot))

