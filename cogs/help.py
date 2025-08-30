import discord
from discord.ext import commands
from collections import defaultdict
import asyncio

# A custom View that holds the dropdown and buttons for the help command
class HelpView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=120.0)
        self.bot = bot
        self.author = author
        self.message = None
        self.home_embed = None
        self.add_item(self.category_dropdown())

    async def on_timeout(self):
        # Disable all components when the view times out
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass # Message might have been deleted

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the original command author to interact
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't use this help menu.", ephemeral=True)
            return False
        return True

    def get_categorized_commands(self):
        # Helper to get all commands organized by category, excluding hidden and admin ones
        categorized = defaultdict(list)
        emojis = {
            "Economic": "💰", "Team": "🛡️", "Shop": "🛒", "Market": "📈",
            "Battle": "⚔️", "Bot Commands": "⚙️", "Reference": "📚", "Player Commands": "👤",
            "AI Battle": "🤖"
        }
        for cmd in self.bot.commands:
            if not cmd.hidden and cmd.name != 'help':
                category = getattr(cmd, 'category', cmd.cog_name or 'Uncategorized')
                if category != 'Admin':
                    emoji = emojis.get(category, "❓")
                    categorized[f"{emoji} {category}"].append(cmd)
        return categorized

    def category_dropdown(self):
        # Create the dropdown menu for categories
        categorized = self.get_categorized_commands()
        
        options = [
            discord.SelectOption(label=category, description=f"Commands in this category.", value=category)
            for category in sorted(categorized.keys()) if categorized[category]
        ]
        
        select = discord.ui.Select(
            placeholder="Choose a command category...",
            options=options,
            custom_id="help_category_select"
        )
        select.callback = self.on_category_select
        return select

    @discord.ui.button(label="Home", style=discord.ButtonStyle.green, custom_id="help_home_button", row=1)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Callback for the "Home" button
        if self.home_embed:
            await interaction.response.edit_message(embed=self.home_embed)

    async def on_category_select(self, interaction: discord.Interaction):
        # Callback for when a category is selected from the dropdown
        category_name = interaction.data['values'][0]
        prefix = self.bot.config.get('PREFIX', '!')
        
        embed = discord.Embed(
            title=f"{category_name} Commands",
            color=discord.Color.blue()
        )
        
        categorized = self.get_categorized_commands()
        commands_in_category = sorted(categorized.get(category_name, []), key=lambda c: c.name)

        if not commands_in_category:
            embed.description = "No commands found in this category."
        else:
            # Build a single description string for a cleaner, more organized look
            description_lines = []
            for command in commands_in_category:
                help_text = command.help.split('-')[1].strip() if '-' in command.help else command.help
                signature = f"{command.name} {command.signature}".strip()
                aliases = f" (Aliases: {', '.join(f'`{a}`' for a in command.aliases)})" if command.aliases else ""
                
                command_line = f"**`{prefix}{signature}`**{aliases}"
                description_line = f"```{help_text}```"
                description_lines.append(f"{command_line}\n{description_line}")
            embed.description = "\n".join(description_lines)
            embed.set_footer(text=f"Use {prefix}help <command> for more details on a specific command.")
        
        await interaction.response.edit_message(embed=embed)


class HelpCog(commands.Cog, name="Help"):
    """The new, interactive help command."""
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.get_command('help')
        bot.remove_command('help')

    @commands.command(name='help', help="Shows this interactive help menu.")
    async def help(self, ctx, *, command_name: str = None):
        """Shows details about a command or an interactive category list."""
        prefix = self.bot.config.get('PREFIX', '!')

        if command_name:
            command = self.bot.get_command(command_name.lower())
            if command and not command.hidden and command.name != 'help':
                embed = self.get_command_help_embed(command, prefix)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Sorry, I couldn't find a command named `{command_name}`.")
        else:
            view = HelpView(self.bot, ctx.author)
            
            embed = discord.Embed(
                title="🔮 Bot Help Menu",
                description=f"Welcome! I am a game bot with many features.\n\nUse the dropdown menu below to browse command categories, or use `{prefix}help <command>` for details on a specific command.",
                color=discord.Color.from_rgb(88, 101, 242)
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text="This menu will time out after 2 minutes of inactivity.")

            view.home_embed = embed
            message = await ctx.send(embed=embed, view=view)
            view.message = message

    def get_command_help_embed(self, command, prefix):
        """Generates a detailed embed for a single command."""
        aliases = ", ".join([f"`{alias}`" for alias in command.aliases]) if command.aliases else "None"
        usage = f"`{prefix}{command.qualified_name} {command.signature}`"
        help_text = command.help.split('-')[1].strip() if '-' in command.help else "No detailed description provided."

        embed = discord.Embed(
            title=f"📜 Command: `{command.name}`",
            description=help_text,
            color=discord.Color.green()
        )
        embed.add_field(name="Usage", value=usage, inline=False)

        # Special case for the market command to explain filters
        if command.qualified_name == 'market view':
            filter_examples = (
                "`--atk > 30` (Attack IV greater than 30)\n"
                "`--spd 31` (Speed IV is exactly 31)\n"
                "`--iv < 80` (Total IV less than 80%)"
            )
            embed.add_field(name="Filtering", value=filter_examples, inline=False)

        embed.add_field(name="Aliases", value=aliases, inline=False)
        
        category = getattr(command, 'category', command.cog_name)
        if category:
            embed.add_field(name="Category", value=category, inline=False)
            
        return embed
    
    def cog_unload(self):
        self.bot.remove_command('help')
        if self._original_help_command:
            self.bot.add_command(self._original_help_command)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))

