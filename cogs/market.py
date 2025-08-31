# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import database as db
import re

class Market(commands.Cog, name="Market"):
    """Commands for the player-driven market."""
    def __init__(self, bot):
        self.bot = bot

    def _apply_market_filters(self, listings, filter_string):
        """Apply PokéTwo-style filters to market listings."""
        if not filter_string:
            return listings
        
        filtered = []
        for listing in listings:
            char = listing['character_data']
            include = True
            
            # Split filters by spaces, but handle quoted strings
            import shlex
            try:
                filter_parts = shlex.split(filter_string.lower())
            except ValueError:
                filter_parts = filter_string.lower().split()
            
            for filter_part in filter_parts:
                if ':' in filter_part:
                    # Handle key:value filters
                    key, value = filter_part.split(':', 1)
                    
                    if key == 'name':
                        if value not in char['name'].lower():
                            include = False
                            break
                    elif key == 'level':
                        if str(char['level']) != value:
                            include = False
                            break
                    elif key == 'price':
                        if str(listing['price']) != value:
                            include = False
                            break
                elif filter_part.startswith('level'):
                    # Handle level comparisons
                    if '>=' in filter_part:
                        try:
                            min_level = int(filter_part.split('>=')[1])
                            if char['level'] < min_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<=' in filter_part:
                        try:
                            max_level = int(filter_part.split('<=')[1])
                            if char['level'] > max_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '>' in filter_part:
                        try:
                            min_level = int(filter_part.split('>')[1])
                            if char['level'] <= min_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<' in filter_part:
                        try:
                            max_level = int(filter_part.split('<')[1])
                            if char['level'] >= max_level:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                elif filter_part.startswith('price'):
                    # Handle price comparisons
                    if '>=' in filter_part:
                        try:
                            min_price = int(filter_part.split('>=')[1])
                            if listing['price'] < min_price:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<=' in filter_part:
                        try:
                            max_price = int(filter_part.split('<=')[1])
                            if listing['price'] > max_price:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '>' in filter_part:
                        try:
                            min_price = int(filter_part.split('>')[1])
                            if listing['price'] <= min_price:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<' in filter_part:
                        try:
                            max_price = int(filter_part.split('<')[1])
                            if listing['price'] >= max_price:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                elif filter_part.startswith('iv'):
                    # Handle IV comparisons
                    if '>=' in filter_part:
                        try:
                            min_iv = float(filter_part.split('>=')[1])
                            if char['iv'] < min_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<=' in filter_part:
                        try:
                            max_iv = float(filter_part.split('<=')[1])
                            if char['iv'] > max_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '>' in filter_part:
                        try:
                            min_iv = float(filter_part.split('>')[1])
                            if char['iv'] <= min_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                    elif '<' in filter_part:
                        try:
                            max_iv = float(filter_part.split('<')[1])
                            if char['iv'] >= max_iv:
                                include = False
                                break
                        except (ValueError, IndexError):
                            continue
                else:
                    # Handle simple name filter
                    if filter_part not in char['name'].lower():
                        include = False
                        break
            
            if include:
                filtered.append(listing)
        
        return filtered

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

    @market.command(name='view', help="!market view [filters] - View market listings with optional filters.")
    async def market_view(self, ctx, *, filters: str = None):
        import math
        import asyncio
        
        listings = db.get_all_market_listings()
        if not listings:
            await ctx.send("The market is currently empty."); return

        # Apply enhanced filters
        filtered_listings = self._apply_market_filters(listings, filters)
        
        if not filtered_listings:
            await ctx.send("No listings match your filters."); return

        # Sort by price (ascending) by default
        filtered_listings.sort(key=lambda x: x['price'])

        # Pagination setup
        listings_per_page = 8
        total_pages = math.ceil(len(filtered_listings) / listings_per_page)
        current_page = 0

        async def create_market_embed(page_num):
            start_idx = page_num * listings_per_page
            end_idx = start_idx + listings_per_page
            page_listings = filtered_listings[start_idx:end_idx]

            embed = discord.Embed(
                title="🏪 Player Market",
                description=f"Page {page_num + 1}/{total_pages} • {len(filtered_listings)} listings" + (f" (filtered)" if filters else ""),
                color=discord.Color.blue()
            )

            listing_text = []
            for listing in page_listings:
                char = listing['character_data']
                try:
                    seller = await self.bot.fetch_user(listing['seller_id'])
                    seller_name = seller.display_name[:12]
                except discord.NotFound:
                    seller_name = "Unknown"

                listing_text.append(
                    f"**#{listing['listing_id']}** | **{char['name']}** Lvl {char['level']} ({char['iv']}% IV)\n"
                    f"💰 {listing['price']:,} coins | 👤 {seller_name}\n"
                )

            embed.description += "\n\n" + "\n".join(listing_text)
            
            if filters:
                embed.set_footer(text=f"Filters: {filters} • Use reactions to navigate • !market buy <id>")
            else:
                embed.set_footer(text="Add filters: !market view name:Naruto level>50 price<5000 • Use reactions to navigate")
            
            return embed

        if total_pages == 1:
            embed = await create_market_embed(0)
            await ctx.send(embed=embed)
            return

        message = await ctx.send(embed=await create_market_embed(current_page))
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return (user == ctx.author and 
                   str(reaction.emoji) in ['◀️', '▶️'] and 
                   reaction.message.id == message.id)

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                if str(reaction.emoji) == '▶️' and current_page < total_pages - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                
                await message.edit(embed=await create_market_embed(current_page))
                await message.remove_reaction(reaction, user)
                
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break
            
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

