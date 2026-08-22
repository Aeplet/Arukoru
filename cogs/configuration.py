import discord
from discord import app_commands
from discord.ext import commands

import utils.database as database
from utils.enums import LogChannelType
from utils.helpers import get_log_channel_from_database
from utils.channels import log_channels, honeypot_channels

@app_commands.default_permissions(administrator=True)
class Configuration(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        # log channels
        for key, cached_channel in list(log_channels.items()):
            if cached_channel.id == channel.id:
                del log_channels[key]
        # honeypot channels
        for key, cached_channel in list(honeypot_channels.items()):
            if cached_channel.id == channel.id:
                del honeypot_channels[key]
        

    @app_commands.guild_only()
    @app_commands.describe(log_channel_type="Which log channel to set the ID for", channel="The channel to set the log channel to")
    @app_commands.command(name="set-log-channel", description="Update log channels for this server")
    async def set_log_channel_command(self, interaction: discord.Interaction, log_channel_type: LogChannelType, channel: discord.TextChannel):
        # delete and remake it. best option here
        await database.execute(query="DELETE FROM server_log_channels WHERE guild_id = ? AND log_channel_type = ?", parameters=(interaction.guild.id, log_channel_type.value,))
        await database.execute(query="INSERT INTO server_log_channels (guild_id, channel_id, log_channel_type) VALUES (?, ?, ?)", parameters=(interaction.guild.id, channel.id, log_channel_type.value,))
        log_channels[(interaction.guild.id, log_channel_type)] = channel # I almost forgot this lol

        # fetch to make sure it actually worked
        updated_channel = await database.fetch_one(query="SELECT channel_id FROM server_log_channels WHERE guild_id = ? AND log_channel_type = ?", parameters=(interaction.guild.id, log_channel_type.value,))
        if updated_channel and updated_channel[0] == channel.id:
            await interaction.response.send_message(f"Successfully updated log channel {log_channel_type.name} to {channel.mention}!", ephemeral=True)
            return
        await interaction.response.send_message(f"Failed to update {log_channel_type.name} to {channel.mention}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to set the honeypot channel to")
    @app_commands.command(name="set-honeypot-channel", description="Set the server's honeypot channel")
    async def set_honeypot_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.execute(query="DELETE FROM honeypot_channels WHERE guild_id = ?", parameters=(interaction.guild.id,))
        await database.execute(query="INSERT INTO honeypot_channels (guild_id, honeypot_channel_id) VALUES (?, ?)", parameters=(interaction.guild.id, channel.id,))
        honeypot_channels[interaction.guild.id] = channel

        # fetch to make sure it actually worked
        updated_channel = await database.fetch_one(query="SELECT honeypot_channel_id FROM honeypot_channels WHERE guild_id = ?", parameters=(interaction.guild.id,))
        if updated_channel and updated_channel[0] == channel.id:
            await interaction.response.send_message(f"Successfully updated honeypot channel to {channel.mention}!", ephemeral=True)
            return
        await interaction.response.send_message(f"Failed to update honeypot channel to {channel.mention}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.describe(instructions="New appeal instructions for this server")
    @app_commands.command(name="set-appeal-instructions", description="Update the instructions sent to appeal in ban DMs for this server")
    async def set_appeal_instructions_command(self, interaction: discord.Interaction, instructions: str):
        if len(instructions) > 1000:
            await interaction.response.send_message(f"Instructions must be a max of 1000 characters.", ephemeral=True)
            return
        await database.execute(query="DELETE FROM appeal_instructions WHERE guild_id = ?", parameters=(interaction.guild.id,))
        await database.execute(query="INSERT INTO appeal_instructions (guild_id, appeal_instructions_text) VALUES (?, ?)", parameters=(interaction.guild.id, instructions,))

        # fetch to make sure it actually worked
        updated_instructions = await database.fetch_one(query="SELECT appeal_instructions_text FROM appeal_instructions WHERE guild_id = ?", parameters=(interaction.guild.id,))
        if updated_instructions and updated_instructions[0] == instructions:
            await interaction.response.send_message(f"Successfully updated appeal instructions to `{instructions}`!", ephemeral=True)
            return
        await interaction.response.send_message(f"Failed to update appeal instructions to `{instructions}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Configuration(bot))