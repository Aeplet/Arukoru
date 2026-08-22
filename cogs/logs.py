import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt

from constants import GUILD_JOIN_LOGS_CHANNEL_ID, DEV_GUILD_ID
from utils.channels import get_log_channel
from utils.enums import ServerAction, ActionType, LogChannelType, ServerJoinLog
from utils.helpers import post_member_update_log, post_member_role_update, post_server_log, post_action_log, post_server_join_log, is_guild_allowed

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if entry.action == discord.AuditLogAction.ban or entry.action == discord.AuditLogAction.kick or entry.action == discord.AuditLogAction.unban:
            if entry.user.id == self.bot.user.id:
                return # don't log our bans/kicks done by the bot, the bot already does that
            target = self.bot.get_user(entry.target.id) or await self.bot.fetch_user(entry.target.id)
            action = None
            match (entry.action):
                case discord.AuditLogAction.kick:
                    action = ActionType.Kick
                case discord.AuditLogAction.unban:
                    action = ActionType.Unban
                case discord.AuditLogAction.ban:
                    action = ActionType.Ban
                case _:
                    raise ValueError(f"Unknown audit log entry type {entry}")
            await post_action_log(action=action, channel=await get_log_channel(guild=entry.guild, log_channel_type=LogChannelType.ModLogs), color=discord.Color.red(), target=target, author=entry.user, reason=entry.reason)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await post_server_log(serverAction=ServerAction.Ban, channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=user)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await post_server_log(serverAction=ServerAction.Unban, channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=user)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_allowed = await is_guild_allowed(guild_id=guild.id) or guild.id == DEV_GUILD_ID
        if not guild_allowed:
            try:
                await guild.leave()
            except discord.HTTPException as failed_to_leave_exception:
                await self.bot.guild_join_logs_channel.send(f"<@82870140068171776> guild join leave failed: {failed_to_leave_exception}")
        await post_server_join_log(serverJoinLog=ServerJoinLog.Join, guild=guild, channel=self.bot.guild_join_logs_channel)

    # leave guilds we don't know. seperate from the main on_ready.
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            guild_allowed = await is_guild_allowed(guild_id=guild.id) or guild.id == DEV_GUILD_ID
            if not guild_allowed:
                try:
                    await guild.leave()
                except discord.HTTPException as failed_to_leave_exception:
                    await self.bot.guild_join_logs_channel.send(f"<@82870140068171776> guild leave failed: {failed_to_leave_exception}")

    @commands.Cog.listener()
    async def on_member_update(self, old_member: discord.Member, new_member: discord.Member):
        guild = old_member.guild
        if old_member.accent_color != new_member.accent_color or old_member.accent_colour != new_member.accent_colour:
            await post_member_update_log(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_field="Accent Color", old_value=str(old_member.accent_color), new_value=str(new_member.accent_color))
        if old_member.pending != new_member.pending:
            await post_member_update_log(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_field="Pending Verification", old_value=old_member.pending, new_value=new_member.pending)
        if old_member.nick != new_member.nick:
            await post_member_update_log(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_field="Nickname", old_value=old_member.display_name, new_value=new_member.display_name)
        if old_member.premium_since != new_member.premium_since:
            await post_member_update_log(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_field="Boosting Date", old_value=old_member.premium_since, new_value=new_member.premium_since)
        if old_member.roles != new_member.roles:
            old_roles = {role.id: role for role in old_member.roles}
            new_roles = {role.id: role for role in new_member.roles}
            
            added = [role for role_id, role in new_roles.items() if role_id not in old_roles]
            removed = [role for role_id, role in old_roles.items() if role_id not in new_roles]
            if added:
                updated_value = [role.name for role in added]
                await post_member_role_update(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_role=updated_value, added=True)
            if removed:
                updated_value = [role.name for role in removed]
                await post_member_role_update(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_role=updated_value, added=False)
        if old_member.timed_out_until != new_member.timed_out_until:
            old_timed_out = format_dt(old_member.timed_out_until) if old_member.timed_out_until is not None else old_member.timed_out_until
            new_timed_out = format_dt(new_member.timed_out_until) if new_member.timed_out_until is not None else new_member.timed_out_until
            await post_member_update_log(channel=await get_log_channel(guild=guild, log_channel_type=LogChannelType.ServerLogs), target=old_member, updated_field="Timed Out Until", old_value=old_timed_out, new_value=new_timed_out)


async def setup(bot):
    await bot.add_cog(Logs(bot))