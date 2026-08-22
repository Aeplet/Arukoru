import discord
from discord import app_commands, __version__ as discordpy_version
from discord.utils import format_dt
from discord.ext import commands
import sys
from subprocess import call

from constants import DEV_GUILD_ID
from utils.helpers import is_bot_developer_app_check, is_guild_allowed
import utils.database as database

@app_commands.guilds(discord.Object(id=DEV_GUILD_ID))
class Dev(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bot-username", description="Set bot username")
    @is_bot_developer_app_check()
    async def set_bot_username_command(self, interaction: discord.Interaction, new_username: str):
        await interaction.response.defer(ephemeral=True)
        await self.bot.user.edit(username=new_username)
        await interaction.followup.send(f"Successfully updated bot username to {new_username}!")

    @app_commands.command(name="bot-avatar", description="Set bot avatar")
    @is_bot_developer_app_check()
    async def set_bot_avatar(self, interaction: discord.Interaction, file: discord.Attachment):
        if not file.content_type or file.content_type not in (
            "image/jpeg",
            "image/png",
            "image/gif",
        ):
            return await interaction.response.send_message(
                "File provided is not a valid image.", ephemeral=True
            )

        image_bytes = await file.read()
        try:
            await self.bot.user.edit(avatar=image_bytes)
        except ValueError:
            await interaction.response.send_message(
                "The image has a invalid format.", ephemeral=True
            )
        except discord.HTTPException as exc:
            embed = create_error_embed(interaction, exc)
            await interaction.response.send_message(
                "Failure to edit the bot's profile.",
                embed=embed,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Profile picture changed successfully.", ephemeral=True
            )
    
    @app_commands.command(name="env",  description="Information about the environment the bot is running under")
    async def env_command(self, interaction: discord.Interaction):
        python_version = sys.version.split()[0]
        message = f'''
        Python {python_version}\ndiscord.py {discordpy_version}'''
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="pull", description="Pull changes from GitHub")
    @is_bot_developer_app_check()
    async def pull_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message = await interaction.followup.send(content="Pulling changes...")
        call(['git', 'pull'])
        await message.edit(content="Changes pulled! Restarting bot...")
        await self.bot.close()

    @app_commands.command(name="quit", description="Quits the bot with bot.close()")
    @is_bot_developer_app_check()
    async def quit_bot_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("Closing bot...")
        self.bot.close()
    
    @is_bot_developer_app_check()
    @app_commands.describe(guild_id="The ID of the guild/server to allow the bot to be used in")
    @app_commands.command(name="allow-guild", description="Allow the bot to be used in a guild")
    async def allow_guild_command(self, interaction: discord.Interaction, guild_id: str):
        guild_id = int(guild_id)
        if await is_guild_allowed(guild_id=guild_id):
            raise ValueError("This guild is already allowed.")
        await database.execute(query="INSERT INTO allowed_guilds (guild_id) VALUES (?)", parameters=(guild_id,))
        await interaction.response.send_message(f"Successfully allowed guild {guild_id} for bot usage!")

    @is_bot_developer_app_check()
    @app_commands.describe(guild_id="The ID of the guild/server to unallow the bot to be used in")
    @app_commands.command(name="unallow-guild", description="Stop allowing the bot to be used in a guild")
    async def unallow_guild_command(self, interaction: discord.Interaction, guild_id: str):
        guild_id = int(guild_id)
        if not await is_guild_allowed(guild_id=guild_id):
            raise ValueError("This guild is not allowed.")
        await database.execute(query="DELETE FROM allowed_guilds WHERE guild_id = ?", parameters=(guild_id,))
        # also leave the guild if the bot is in it
        guild = bot.get_guild(guild_id)
        if guild is None:
            try:
                guild = await bot.fetch_guild(guild_id)
            except discord.NotFound:
                guild = None
            except discord.Forbidden:
                guild = None

        if guild is not None:
            await guild.leave()
        await interaction.response.send_message(f"Successfully unallowed guild {guild_id} for bot usage!")

async def setup(bot):
    await bot.add_cog(Dev(bot))