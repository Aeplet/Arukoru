import discord
from discord import app_commands, __version__ as discordpy_version
from discord.utils import format_dt
from discord.ext import commands

import sys
from subprocess import call

from utils.helpers import is_bot_developer_app_check

python_version = sys.version.split()[0]

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

async def setup(bot):
    await bot.add_cog(Dev(bot))