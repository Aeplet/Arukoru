import discord

from utils.helpers import get_log_channel_from_database, get_honeypot_channel_from_database
from utils.enums import LogChannelType

log_channels: dict[tuple[int, LogChannelType], discord.TextChannel] = {} # for tuple: guild id, log channel type
honeypot_channels: dict[int, discord.TextChannel] = {} # guild id, channel

async def get_log_channel(guild: discord.Guild, log_channel_type: LogChannelType) -> discord.TextChannel | None:
    channel = log_channels.get((guild.id, log_channel_type))
    if channel:
        return channel
    # we must fetch it ourself
    channel = await get_log_channel_from_database(guild_id=guild.id, log_channel_type=log_channel_type)
    if channel:
        try:
            channel = guild.get_channel(channel) or await guild.fetch_channel(channel)
            log_channels[(guild.id, log_channel_type)] = channel
            return channel
        except (discord.NotFound, discord.Forbidden):
            return None
    return None

async def get_honeypot_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = honeypot_channels.get(guild.id)
    if channel:
        return channel
    # we must fetch it ourself
    channel = await get_honeypot_channel_from_database(guild_id=guild.id)
    if channel:
        try:
            channel = guild.get_channel(channel) or await guild.fetch_channel(channel)
            honeypot_channels[guild.id] = channel
            return channel
        except (discord.NotFound, discord.Forbidden):
            return None
    return None