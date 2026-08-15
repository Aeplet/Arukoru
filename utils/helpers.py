import discord
from discord import app_commands
from discord.utils import format_dt
from discord.ext import commands

import sys

from constants import BOT_DEVELOPERS, MODMAIL_USER_ID, KILLBOX_DELETE_MESSAGE_SECONDS
from utils.enums import ActionType, ServerAction, MessageLog, Restriction
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

async def post_honeypot_log(user: discord.User, channel: discord.TextChannel, reason: str):
    embed = discord.Embed(
        title=f"Member Triggered Honeypot",
        description=f"Reason: {reason}",
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user.name}`) (`{user.id}`)", inline=True) 
    embed.set_thumbnail(url=user.display_avatar.url)

    await channel.send(embeds=[embed])

async def handle_honeypot_action(user: discord.User, guild: discord.Guild, reason: str, log_channel: discord.TextChannel): # reason is string because I'm lazy :)
    if is_staff(member=user): # staff are immune
        return
    await guild.ban(user, reason="Triggered honeypot, banning to purge messages", delete_message_seconds=KILLBOX_DELETE_MESSAGE_SECONDS)
    await guild.unban(user, reason="Triggered honeypot, unbanning after purging messages")
    await post_honeypot_log(user=user, channel=log_channel, reason=reason)

async def post_action_log(action: ActionType, channel: discord.TextChannel, author: discord.User = None, reason: str = None, target: discord.User = None, color: discord.Color = None):
    embed = discord.Embed(
        title=f"Member {get_string_by_action_type(action)}",
        description=f"Reason: {reason}",
        color=color
    )

    if target is not None:
        embed.add_field(name="User", value=f"{target.mention} (`{target.name}`) (`{target.id}`)", inline=True) 
        embed.set_thumbnail(url=target.display_avatar.url)
    if author is not None:
        embed.add_field(name="Author", value=f"{author.mention} (`{author.name}`) (`{author.id}`)", inline=True)    

    await channel.send(embeds=[embed])

async def post_member_update_log(channel: discord.Channel, target: discord.User, updated_field: str, old_value: str, new_value: str, note: str = None, color: discord.Color = None):
    embed = discord.Embed(
        title=f"Member Update",
        description=f"{updated_field} Updated",
        color=color
    )

    embed.add_field(name="User", value=f"{target.mention} (`{target.name}`) (`{target.id}`)", inline=True) 
    embed.set_thumbnail(url=target.display_avatar.url)

    embed.add_field(name="Old Value", value=old_value, inline=True)
    embed.add_field(name="New Value", value=new_value, inline=True)

    await channel.send(embeds=[embed])

async def post_member_role_update(channel: discord.TextChannel, target: discord.User, updated_role: str, added: bool, note: str = None, color: discord.Color = None):
    embed = discord.Embed(
        title=f"Member Role Update",
        description=f"Roles Updated",
        color=color
    )

    embed.add_field(name="User", value=f"{target.mention} (`{target.name}`) (`{target.id}`)", inline=True) 
    embed.set_thumbnail(url=target.display_avatar.url)
    field_name = "Roles Added" if added else "Roles Removed"
    embed.add_field(name=field_name, value=updated_role, inline=True)

    await channel.send(embeds=[embed])

async def post_server_log(bot: commands.Bot, serverAction: ServerAction, channel: discord.TextChannel, target: discord.User = None, note: str = None, color: discord.Color = None):
    embed = discord.Embed(
        title=f"{get_string_by_server_action(serverAction)}",
        description=f"Note: {note}",
        color=color
    )
    
    if target is not None:
        embed.add_field(name="User", value=f"{target.mention} (`{target.name}`) (`{target.id}`)", inline=True) 
        embed.set_thumbnail(url=target.display_avatar.url)

    await channel.send(embeds=[embed])

async def post_message_log(bot: commands.Bot, messageLog: MessageLog, channel: discord.TextChannel, color: discord.Color, message: discord.Message, new_message: discord.Message = None, note: str = None):
    embed = discord.Embed(
        title=f"{get_string_by_message_log(messageLog)}",
        description=f"Note: {note}",
        color=color
    )

    author = message.author

    embed.add_field(name="Author", value=f"{author.mention} (`{author.name}`) (`{author.id}`)", inline=False)
    
    if not new_message:
        embed.add_field(name="Message Content", value=f"{message.content}", inline=False)
    else:
        embed.add_field(name="Old Message Content", value=f"{message.content}", inline=True)
        embed.add_field(name="New Message Content", value=f"{new_message.content}", inline=True)
    
    embed.add_field(name="Message Date", value=format_dt(message.created_at), inline=False)

    embed.add_field(name="Message Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="Message Link", value=f"[Jump to message]({message.jump_url})", inline=True)
    embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)

    await channel.send(embeds=[embed])

async def handle_warn_automated_action(user: discord.User, guild: discord.Guild, warn_count: int):
    if warn_count >= 5:
        await guild.ban(user, reason="Reached 5+ warnings", delete_message_seconds=0)
        return
    elif warn_count >= 3 and guild.get_member(user.id):
        await guild.kick(user, reason=f"Reached {warn_count} warnings")
        return
    return

# rare case of using a direct user id, no point of the full User object here
async def get_user_warning_count(user_id: int):
    warn_count = (await database.fetch_one(query="SELECT COUNT(*) FROM warnings WHERE user_id = ?", parameters=(user_id,)))[0] or 0
    return warn_count

async def get_all_user_warnings(user_id: int):
    warnings = await database.fetch_all(query="SELECT * from warnings WHERE user_id = ?", parameters=(user_id,))
    return warnings

async def get_latest_user_warning(user_id: int):
    warning = await database.fetch_one(query="SELECT * FROM warnings WHERE user_id = ? ORDER BY warn_id DESC LIMIT 1", parameters=(user_id,))
    return warning

async def does_warn_exist(warn_id: int):
    result = await database.fetch_one(query="SELECT 1 FROM warnings WHERE warn_id = ? LIMIT 1", parameters=(warn_id,))
    return result is not None

# same thing here, we only need the guild id
async def is_guild_invite_whitelisted(guild_id: int):
    result = await database.fetch_one(query="SELECT 1 FROM whitelisted_guilds WHERE guild_id = ? LIMIT 1", parameters=(guild_id,))
    return result is not None

async def add_restriction(user: discord.User, restriction_type: Restriction):
    print("empty for now")