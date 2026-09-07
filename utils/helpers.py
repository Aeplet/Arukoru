import discord
from discord import app_commands
from discord.utils import format_dt
from discord.ext import commands

import sys

from constants import BOT_DEVELOPERS, KILLBOX_DELETE_MESSAGE_SECONDS
from utils.enums import ActionType, ServerAction, MessageLog, Restriction, LogChannelType, ServerJoinLog
import utils.database as database

class AppNotBotDeveloper(app_commands.CheckFailure):
    message: str

class AppNotStaffCheck(app_commands.CheckFailure):
    message: str

class DateOrTimeToSecondsConverter:
    @staticmethod
    def parse(value: str) -> int:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        total_seconds = 0
        
        for token in value.lower().split():
            unit = token[-1]
            if unit not in units:
                raise ValueError("Invalid time unit")
                
            amount = int(token[:-1])
            total_seconds += amount * units[unit]
            
        return total_seconds

class DurationTransformer(app_commands.Transformer):
    async def transform(self, interaction, value: str) -> int:
        return DateOrTimeToSecondsConverter.parse(value)

def get_string_by_action_type(actionType: ActionType) -> str:
    match actionType:
        case ActionType.Ban:
            return "Banned"
        case ActionType.Kick:
            return "Kicked"
        case ActionType.ScamKick:
            return "Scamkicked"
        case ActionType.Unban:
            return "Unbanned"
        case ActionType.Timeout:
            return "Timed Out"
        case ActionType.TimeoutRemoval:
            return "Timeout Removed"
        case ActionType.Warn:
            return "Warned"
        case ActionType.WarnRemove:
            return "Warn Removed"
        case _:
            return "(Unknown Action Type)"

def get_string_by_server_action(serverAction: ServerAction) -> str:
    match serverAction:
        case ServerAction.Join:
            return "Member Joined"
        case ServerAction.Leave:
            return "Member Left"
        case ServerAction.Ban:
            return "Member Banned"
        case ServerAction.Unban:
            return "Member Unbanned"
        case ServerAction.KillboxTrigger:
            return "Member Triggered Killbox"
        case _:
            return "(Unknown Action Type)"

def get_string_by_message_log(messageLog: MessageLog) -> str:
    match messageLog:
        case MessageLog.Delete:
            return "Message Deleted"
        case MessageLog.Edit:
            return "Message Edited"
        case _:
            return "(Unknown Action Type)"

def get_string_by_server_join_log(serverJoinLog: ServerJoinLog) -> str:
    match serverJoinLog:
        case ServerJoinLog.Join:
            return "Server Joined"
        case ServerJoinLog.Leave:
            return "Server Left"
        case _:
            return "(Unknown Action Type)"

def is_bot_developer_app_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in BOT_DEVELOPERS:
            return True
        raise AppNotBotDeveloper("You are not a bot developer, and therefore can't use this command.")
    return app_commands.check(predicate)

def is_staff(member: discord.Member):
    if isinstance(member, discord.Member):
        if member.guild_permissions.moderate_members:
            return True
    return False

async def check_staff_target(interaction: discord.Interaction, user: discord.User):
    if isinstance(user, discord.Member):
        if user.guild_permissions.moderate_members:
            await interaction.response.send_message("You cannot perform this action on this user.", ephemeral=True)
            return True
    return False

async def post_honeypot_log(user: discord.User, reason: str, channel: discord.TextChannel = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"Member Triggered Honeypot",
        description=f"Reason: {reason}",
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user}`) (`{user.id}`)", inline=True) 
    embed.set_thumbnail(url=user.display_avatar.url)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def handle_honeypot_action(user: discord.User, guild: discord.Guild, reason: str, log_channel: discord.TextChannel): # reason is string because I'm lazy :)
    if is_staff(member=user): # staff are immune
        return
    try:
        await guild.ban(user, reason="Triggered honeypot, banning to purge messages", delete_message_seconds=KILLBOX_DELETE_MESSAGE_SECONDS)
        await guild.unban(user, reason="Triggered honeypot, unbanning after purging messages")
        await post_honeypot_log(user=user, channel=log_channel, reason=reason)
    except discord.Forbidden:
        pass

async def post_action_log(action: ActionType, channel: discord.TextChannel = None, author: discord.User = None, reason: str = None, target: discord.User = None, color: discord.Color = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"Member {get_string_by_action_type(action)}",
        description=f"Reason: {reason}",
        color=color
    )

    if target is not None:
        embed.add_field(name="User", value=f"{target.mention} (`{target}`) (`{target.id}`)", inline=True) 
        embed.set_thumbnail(url=target.display_avatar.url)
    if author is not None:
        embed.add_field(name="Author", value=f"{author.mention} (`{author}`) (`{author.id}`)", inline=True)    

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def post_member_update_log(target: discord.User, updated_field: str, old_value: str, new_value: str, channel: discord.TextChannel = None, note: str = None, color: discord.Color = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"Member Update",
        description=f"{updated_field} Updated",
        color=color
    )

    embed.add_field(name="User", value=f"{target.mention} (`{target}`) (`{target.id}`)", inline=True) 
    embed.set_thumbnail(url=target.display_avatar.url)

    embed.add_field(name="Old Value", value=old_value, inline=True)
    embed.add_field(name="New Value", value=new_value, inline=True)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def post_member_role_update(target: discord.User, updated_role: str, added: bool, channel: discord.TextChannel = None, note: str = None, color: discord.Color = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"Member Role Update",
        description=f"Roles Updated",
        color=color
    )

    embed.add_field(name="User", value=f"{target.mention} (`{target}`) (`{target.id}`)", inline=True) 
    embed.set_thumbnail(url=target.display_avatar.url)
    field_name = "Roles Added" if added else "Roles Removed"
    embed.add_field(name=field_name, value=updated_role, inline=True)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def post_server_log(serverAction: ServerAction, channel: discord.TextChannel = None, target: discord.User = None, note: str = None, color: discord.Color = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"{get_string_by_server_action(serverAction)}",
        description=f"{note}",
        color=color
    )
    
    if target is not None:
        embed.add_field(name="User", value=f"{target.mention} (`{target}`) (`{target.id}`)", inline=True) 
        embed.set_thumbnail(url=target.display_avatar.url)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def post_server_join_log(serverJoinLog: ServerJoinLog, guild: discord.Guild, channel: discord.TextChannel = None, note: str = None):
    if channel == None:
        return
    
    embed = discord.Embed(
        title=f"{get_string_by_server_join_log(serverJoinLog)}",
        description=f"Note: {note}",
    )

    embed.add_field(name="Guild", value=f"`{guild.name}` (`{guild.id}`)", inline=False)
    embed.add_field(name="Member Count", value=str(guild.member_count), inline=False)
    embed.add_field(name="Owner", value=f"{guild.owner.mention} (`{guild.owner}`) (`{guild.owner.id}`)", inline=False)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def post_message_log(messageLog: MessageLog, color: discord.Color, message: discord.Message, new_message: discord.Message = None, note: str = None, channel: discord.TextChannel = None):
    if channel == None:
        return
    embed = discord.Embed(
        title=f"{get_string_by_message_log(messageLog)}",
        description=f"Note: {note}",
        color=color
    )

    author = message.author

    embed.add_field(name="Author", value=f"{author.mention} (`{author}`) (`{author.id}`)", inline=False)
    
    if not new_message:
        embed.add_field(name="Message Content", value=f"{message.content}", inline=False)
    else:
        embed.add_field(name="Old Message Content", value=f"{message.content}", inline=True)
        embed.add_field(name="New Message Content", value=f"{new_message.content}", inline=True)
    
    embed.add_field(name="Message Date", value=format_dt(message.created_at), inline=False)

    embed.add_field(name="Message Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="Message Link", value=f"[Jump to message]({message.jump_url})", inline=True)
    embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)

    try:
        await channel.send(embeds=[embed])
    except discord.Forbidden:
        pass # we should probably do something more... idk how to tell them

async def safe_message_delete(message: discord.Message):
    if message.guild is None:
        return # safety
    if not message.channel.permissions_for(message.guild.me).manage_messages:
        return
    try:
        await message.delete()
    except discord.Forbidden:
        pass

# discord.Member because if we only have a discord.User object, we might run into some issues
async def send_dm_message(member: discord.Member, guild: discord.Guild, embeds: list[discord.Embed] = None):
    if member.bot:
        return
    try:
        member = guild.get_member(member.id) or await guild.fetch_member(member.id)
        await member.send(embeds=[e for e in (embeds or []) if e]) # looks weird lol
    except (discord.NotFound, discord.Forbidden):
        pass

async def handle_warn_automated_action(user: discord.User, guild: discord.Guild, warn_count: int):
    if warn_count >= 5:
        try:
            await guild.ban(user, reason="Reached 5+ warnings", delete_message_seconds=0)
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass
        return
    elif warn_count >= 3:
        try:
            await guild.kick(user, reason=f"Reached {warn_count} warnings")
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass
        return
    return

# rare case of using a direct user id, no point of the full User object here
async def get_user_warning_count(user_id: int, guild_id: int):
    warn_count = (await database.fetch_one(query="SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?", parameters=(user_id, guild_id,)))[0] or 0
    return warn_count

async def get_all_user_warnings(user_id: int, guild_id: int):
    warnings = await database.fetch_all(query="SELECT * from warnings WHERE user_id = ? AND guild_id = ?", parameters=(user_id, guild_id,))
    return warnings

async def get_latest_user_warning(user_id: int, guild_id: int):
    warning = await database.fetch_one(query="SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY warn_id DESC LIMIT 1", parameters=(user_id, guild_id,))
    return warning

async def does_warn_exist(warn_id: int):
    result = await database.fetch_one(query="SELECT 1 FROM warnings WHERE warn_id = ? LIMIT 1", parameters=(warn_id,))
    return result is not None

# same thing here, we only need the guild id
async def is_guild_invite_whitelisted(guild_id: int, whitelisted_in_guild_id: int):
    result = await database.fetch_one(query="SELECT 1 FROM whitelisted_guilds WHERE guild_id = ? AND guild_whitelisted_in = ? LIMIT 1", parameters=(guild_id, whitelisted_in_guild_id))
    return result is not None

async def is_guild_allowed(guild_id: int):
    result = await database.fetch_one(query="SELECT 1 FROM allowed_guilds WHERE guild_id = ? LIMIT 1", parameters=(guild_id,))
    return result is not None

async def get_log_channel_from_database(guild_id: int, log_channel_type: LogChannelType):
    result = await database.fetch_one(query="SELECT channel_id FROM server_log_channels WHERE guild_id = ? AND log_channel_type = ?", parameters=(guild_id, log_channel_type.value,))
    return result[0] if result else None 

async def get_honeypot_channel_from_database(guild_id: int):
    result = await database.fetch_one(query="SELECT honeypot_channel_id FROM honeypot_channels WHERE guild_id = ?", parameters=(guild_id,))
    return result[0] if result else None

async def get_appeal_instructions_for_server(guild_id: int):
    result = await database.fetch_one(query="SELECT appeal_instructions_text FROM appeal_instructions WHERE guild_id = ?", parameters=(guild_id,))
    return result[0] if result else None

async def generate_appeal_embed(guild_id: int) -> discord.Embed:
    instructions = await get_appeal_instructions_for_server(guild_id=guild_id)
    if instructions:
        return discord.Embed(
            title=f"Appeal Information",
            description=instructions,
            color=discord.Color.dark_red()
        )
    return None

async def add_restriction(user: discord.User, restriction_type: Restriction, guild_id: int):
    print("empty for now")
