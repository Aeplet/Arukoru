import discord
from discord import app_commands
from discord.utils import format_dt
from discord.ext import commands

import sys
import re
from datetime import datetime, timedelta

from utils.helpers import check_staff_target, is_staff, post_action_log, DurationTransformer, handle_honeypot_action, get_user_warning_count, get_all_user_warnings, is_guild_invite_whitelisted, handle_warn_automated_action, get_latest_user_warning, does_warn_exist, safe_message_delete, generate_appeal_embed, send_dm_message
from utils.enums import ActionType, LogChannelType
from utils.channels import get_log_channel, get_honeypot_channel
import utils.database as database

# TODO: EMBED HELPER FUNCTION

class Mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_discord_invites_message(self, message: discord.Message):
        # todo: some message log bs for this. #message-logs already logs these naturally so for now it's fine?
        if is_staff(member=message.author): # staff immunity
            return

        regex = r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)(?::\d+)?/[\w-]+(?:\?[^\s]*)?" # thanks to shlok
        matches = re.findall(regex, message.content)
        for match in matches:
            try:
                invite = await self.bot.fetch_invite(match)
                if not await is_guild_invite_whitelisted(guild_id=invite.guild.id, whitelisted_in_guild_id=message.guild.id):
                    await safe_message_delete(message=message)
                    return
            except discord.NotFound:
                # it wasn't found who cares
                await safe_message_delete(message=message)
                return
            except discord.HTTPException:
                await safe_message_delete(message=message)
                return
            except ValueError:
                # according to discord.py docs: The url contains an event_id, but scheduled_event_id has also been provided.
                await safe_message_delete(message=message)
                return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # for moderational on_message, ignore DMs or messages from other bots
        if message.guild is None or message.author == message.guild.me:
            return

        # discord invite check
        await self.check_discord_invites_message(message=message)

        # honeypot role
        #role_mentions = message.role_mentions
        #if role_mentions:
        #    for role in role_mentions:
        #        if role.id == HONEYPOT_ROLE_ID:
        #            await safe_message_delete(message=message)
        #           await handle_honeypot_action(user=message.author, guild=message.guild, reason="Pinged honeypot role", log_channel=await get_log_channel(guild=message.guild, log_channel_type=LogChannelType.ModLogs))

        # honeypot/killbox channel:
        if message.channel == await get_honeypot_channel(guild=message.guild):
            await handle_honeypot_action(user=message.author, guild=message.guild, reason="Sent message in honeypot channel", log_channel=await get_log_channel(guild=message.guild, log_channel_type=LogChannelType.ModLogs))

    @commands.Cog.listener()
    async def on_message_edit(old_message: discord.Message, new_message: discord.Message):
        if old_message.guild is None or old_message.author == old_message.guild.me:
            return
        # discord invite check
        await self.check_discord_invites_message(message=message)

    # todo: warn cog
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to warn", reason="The reason to warn the user", skip_action="If the automated action that the warn should apply should be skipped")
    @app_commands.command(name="warn", description="Warn a user. Notifys them via DMs (if possible)")
    async def warn_member_command(self, interaction: discord.Interaction, user: discord.User, reason: str, skip_action: bool = False):
        if await check_staff_target(interaction, user):
            return
        await interaction.response.defer()
        result = await database.execute(query="INSERT INTO warnings (user_id, issuer_id, reason, guild_id) VALUES (?, ?, ?, ?)", parameters=(user.id, interaction.user.id, reason, interaction.guild.id))
        # todo: explain what each warn does
        if isinstance(user, discord.Member):
            information_embed = discord.Embed(
                title=f"You were warned in {interaction.guild.name}.",
                description=f"Reason: {reason}",
                color=discord.Color.red()
            )
            appeals_embed = await generate_appeal_embed(guild_id=interaction.guild.id)
            await send_dm_message(member=user, guild=interaction.guild, embeds=[information_embed, appeals_embed])
        warn_count = await get_user_warning_count(user_id=user.id, guild_id=interaction.guild.id)
        if not skip_action:
            await handle_warn_automated_action(guild=interaction.guild, user=user, warn_count=warn_count)
        await interaction.followup.send(f"{user.mention} ({user.id}) warned. They have been warned {warn_count} times.")
        warn_id = (await get_latest_user_warning(user_id=user.id, guild_id=interaction.guild.id))[0]
        await post_action_log(target=user, action=ActionType.Warn, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), color=discord.Color.orange(), author=interaction.user, reason=f"{reason} (**Warn #{warn_count} | ID {warn_id}**)")

    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(warn_id="The ID of the warn to remove, you can get this via using /warn-list on a user.", reason="Reason for removing the warn")
    @app_commands.command(name="warn-remove", description="Remove a warn from a user")
    async def warn_remove_command(self, interaction: discord.Interaction, warn_id: int, reason: str):
        if not await does_warn_exist(warn_id=warn_id):
            raise ValueError(f"Warn {warn_id} does not exist.")
        await database.execute(query="DELETE FROM warnings WHERE warn_id = ?", parameters=(warn_id,))
        await interaction.response.send_message(f"Successfully removed warn {warn_id}!")
        await post_action_log(action=ActionType.WarnRemove, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), color=discord.Color.orange(), author=interaction.user, reason=f"{reason}\n(**Warn ID: {warn_id}**)")
    
    @app_commands.guild_only()
    @app_commands.describe(user="The user whos warns to check, if not yourself.")
    @app_commands.command(name="warn-list", description="Check your (or another user)'s warns")
    async def list_warns_command(self, interaction: discord.Interaction, user: discord.User = None, ephemeral: bool = False):
        if user == None: # why not
            user = interaction.user
        if not is_staff(member=interaction.user) and user.id != interaction.user.id:
            await interaction.response.send_message("This commmand can only be used on yourself.", ephemeral=True)
            return

        if await get_user_warning_count(user_id=user.id, guild_id=interaction.guild.id) < 1:
            await interaction.response.send_message(f"No warns found for user {user.mention} ({user.id}).", ephemeral=ephemeral)
            return
        
        embed = discord.Embed()
        embed.set_author(name=f"Warns for {user} ({user.id})", icon_url=user.display_avatar.url)
        warnings = await get_all_user_warnings(user_id=user.id, guild_id=interaction.guild.id)
        for count, (warn_id, user_id, issuer_id, reason, guild_id, timestamp) in enumerate(warnings, start=1):
            value = f"Warning ID: {warn_id}\n"
            value += f"Guild ID: {guild_id}\n"
            value += f"Reason: {reason}\n"
            if is_staff(member=interaction.user):
                value += f"Issuer: <@{issuer_id}>"

            embed.add_field(name=f"{count}: <t:{int(datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').timestamp())}>", value=value)
        await interaction.response.send_message(embeds=[embed], ephemeral=ephemeral)

    # this should be moved into an invite cog?
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(guild_id="The ID of the guild/server to whitelist invites for")
    @app_commands.command(name="whitelist-guild-invite", description="Whitelist invites for a guild/server")
    async def whitelist_guild_invite_command(self, interaction: discord.Interaction, guild_id: str):
        guild_id = int(guild_id)
        if await is_guild_invite_whitelisted(guild_id=guild_id, whitelisted_in_guild_id=interaction.guild.id):
            raise ValueError("This guild invite is already whitelisted.")
        await database.execute(query="INSERT INTO whitelisted_guilds (guild_id, adder_id, guild_whitelisted_in) VALUES (?, ?, ?)", parameters=(guild_id, interaction.user.id, interaction.guild.id))
        await interaction.response.send_message(f"Successfully whitelisted guild {guild_id} for invites!")

    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(guild_id="The ID of the guild/server to unwhitelist invites for")
    @app_commands.command(name="unwhitelist-guild-invite", description="Unwhitelist invites for a guild/server")
    async def unwhitelist_guild_invite_command(self, interaction: discord.Interaction, guild_id: str):
        guild_id = int(guild_id)
        if not await is_guild_invite_whitelisted(guild_id=guild_id, whitelisted_in_guild_id=interaction.guild.id):
            raise ValueError("This guild invite is not whitelisted.")
        await database.execute(query="DELETE FROM whitelisted_guilds WHERE guild_id = ? AND guild_whitelisted_in = ?", parameters=(guild_id, interaction.guild.id))
        await interaction.response.send_message(f"Successfully unwhitelisted guild {guild_id} for invites!")

    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.guild_only()
    @app_commands.describe(amount="The amount of messages to purge", channel="The channel to purge messages in, if not the current one")
    @app_commands.command(name="purge", description="Purge a certain amount of the latest messages from a channel. Pinned messages are ignored.")
    async def purge_command(self, interaction: discord.Interaction, amount: int, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        if channel == None:
            channel = interaction.channel
        
        if not channel.permissions_for(interaction.user).manage_messages:
            await interaction.followup.send("You do not have the Manage Messages permission in this channel, and therefore can't use this.", ephemeral=True)
            return

        checks = [lambda m: not m.pinned]

        def check(message):
            return all(c(message) for c in checks)

        try:
            deleted = await channel.purge(limit=amount,
                                          check=check, reason=f"Purged by {interaction.user}")
        except (discord.Forbidden, discord.HTTPException) as exception:
            return await interaction.followup.send(f"Deleting messages failed {exception}", ephemeral=True)
        if deleted:
            # eventually log here something.
            await interaction.followup.send(f"Successfully deleted {len(deleted)} messages in {channel.mention}!")
        else:
            await interaction.followup.send("No messages were deleted.", ephemeral=True)\
        
    # todo: switch to an embed, or hell rewrite user-info
    @app_commands.guild_only()
    @app_commands.command(name="user-info", description="Get user info for a specific user")
    async def user_info_command(self, interaction: discord.Interaction, user: discord.User = None, ephemeral: bool = False):
        if user == None: # why not
            user = interaction.user
        if not is_staff(member=interaction.user) and user.id != interaction.user.id:
            await interaction.response.send_message("This commmand can only be used on yourself.", ephemeral=True)
            return
        guild = interaction.guild
        embed = discord.Embed()
        embed.description = (
            f"**User:** {user.mention}\n"
            f"**User's ID:** `{user.id}`\n"
            f"**Created on:** {format_dt(user.created_at)} ({format_dt(user.created_at, style='R')})\n"
            f"**Default Profile Picture:** {user.default_avatar}\n"
        )
        if isinstance(user, discord.Member):
            embed.description += (
                f"**Join date:** {format_dt(user.joined_at) if user.joined_at else None} ({format_dt(user.joined_at, style='R') if user.joined_at else None})\n"
                f"**Current Status:** {user.status}\n"
                f"**User Activity:** {user.activity}\n"
                f"**Current Display Name:** {user.display_name}\n"
                f"**Nitro Boost Info:** {f'Boosting since {format_dt(user.premium_since)}' if user.premium_since else 'Not a booster'}\n"
                f"**Current Top Role:** {user.top_role}\n"
                f"**Color:** {user.color}\n"
                f"**Profile Picture:** [link]({user.avatar})"
            )
            if user.guild_avatar:
                embed.description += f"\n**Guild Profile Picture:** [link]({user.guild_avatar})"

        try:
            ban = await guild.fetch_ban(user)
            embed.description += f"\n**Ban reason**: {ban.reason}"
        except (discord.NotFound, discord.Forbidden):
            pass
        
        embed.title = f"Info for {'bot' if user.bot else 'user'} {user}"
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to kick", reason="Reason for the kick", silent="Opt out of notifying the user of the kick via DM")
    @app_commands.command(name="kick", description="Kick a user, and send them a direct message with a reason")
    async def kick_user_command(self, interaction: discord.Interaction, user: discord.Member, reason: str = None, silent: bool = False): # a kick needs them to be in the server, so we use discord.Member instead of discord.User
        if await check_staff_target(interaction, user):
            return
        
        if not isinstance(user, discord.Member):
            await interaction.response.send_message(f"{user.mention} ({user.id}) is not in the server!", ephemeral=True)
            return
        
        if not silent:
            information_embed = discord.Embed(
                title=f"You were kicked from {interaction.guild.name}.",
                description=f"Reason: {reason}\n\nYou are able to rejoin the server, however please make sure to read the rules before participating again.",
                color=discord.Color.red()
            )
            await send_dm_message(member=user, guild=interaction.guild, embeds=[information_embed])
        try:
            await interaction.guild.kick(user, reason=reason)
        except discord.errors.Forbidden as forbidden_to_kick_exception:
            await interaction.response.send_message(f"Failed to kick member: {forbidden_to_kick_exception}", ephemeral=True)
            return
        
        await interaction.response.send_message(f"{user} is now gone.")
        await post_action_log(author=interaction.user, target=user, action=ActionType.Kick, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=reason, color=discord.Color.red())

    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to kick")
    @app_commands.command(name="scamkick", description="(ONLY USE FOR SCAMS) Kick a user, and let them know they have been compromised.")
    async def scamkick_user_command(self, interaction: discord.Interaction, user: discord.Member): # a kick needs them to be in the server, so we use discord.Member instead of discord.User
        await interaction.response.defer() # it's been proven that this can take longer than 3 seconds, so this is needed.
        if await check_staff_target(interaction, user):
            return
        if not isinstance(user, discord.Member):
            await interaction.followup.send(f"{user.mention} ({user.id}) is not in the server!", ephemeral=True)
            return
        reason = "Sending or linking scams or spam content, and/or compromised account."
        information_embed = discord.Embed(
            title=f"You were kicked from {interaction.guild.name}.",
            description=f"You were kicked because your account has been compromised and has sent spam or scams in the server.\nYou are able to rejoin the server, but please secure your account, reinstall your operating system, and consider adding two-factor authentication.",
            color=discord.Color.red()
        )
        await send_dm_message(member=user, guild=interaction.guild, embeds=[information_embed])
        try:
            await interaction.guild.ban(user, reason=reason, delete_message_days=1)
            await interaction.guild.unban(user)
        except discord.errors.Forbidden as forbidden_to_kick_exception:
            await interaction.followup.send(f"Failed to kick member: {forbidden_to_kick_exception}")
            return
        
        await interaction.followup.send(f"{user} is now gone.")
        await post_action_log(author=interaction.user, target=user, action=ActionType.ScamKick, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=reason, color=discord.Color.red())

    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to ban", reason="Reason for the ban", remove_messages="Number of days of messages to delete (up to 7 max)", silent="Opt out of notifying the user of the ban via DM")
    @app_commands.command(name="ban", description="Ban a user, and send them a direct message with a reason")
    async def ban_user_command(self, interaction: discord.Interaction, user: discord.User, reason: str = None, remove_messages: app_commands.Range[int, 0, 7] = 0, silent: bool = False):
        if await check_staff_target(interaction, user):
            return

        if isinstance(user, discord.Member) and not silent:
            information_embed = discord.Embed(
                title=f"You were banned from {interaction.guild.name}.",
                description=f"Reason: {reason}",
                color=discord.Color.red()
            )
            appeals_embed = await generate_appeal_embed(guild_id=interaction.guild.id)
            await send_dm_message(member=user, guild=interaction.guild, embeds=[information_embed, appeals_embed])
        
        try:
            await interaction.guild.ban(user, reason=reason, delete_message_days=remove_messages)
        except discord.errors.Forbidden as forbidden_to_ban_exception:
            await interaction.response.send_message(f"Failed to ban member: {forbidden_to_ban_exception}", ephemeral=True)
            return
        
        await interaction.response.send_message(f"{user} is now banned.")
        await post_action_log(author=interaction.user, target=user, action=ActionType.Ban, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=reason, color=discord.Color.red())

    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to unban", reason="Reason to unban the user")
    @app_commands.command(name="unban", description="Unban a user")
    async def unban_user_command(self, interaction: discord.Interaction, user: discord.User, reason: str = None):
        try:
            await interaction.guild.fetch_ban(user)
        except (discord.NotFound):
            return await interaction.response.send_message(f"{user} ({user.id}) is not banned!", ephemeral=True)
        except (discord.Forbidden):
            return await interaction.response.send_message(f"I don't have permission to do this.")
        
        try:
            await interaction.guild.unban(user, reason=reason)
        except discord.errors.Forbidden as forbidden_to_unban_exception:
            await interaction.response.send_message(f"Failed to unban member: {forbidden_to_unban_exception}", ephemeral=True)
            return

        await interaction.response.send_message(f"{user} ({user.id}) is now unbanned.")
        await post_action_log(author=interaction.user, target=user, action=ActionType.Unban, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=reason, color=discord.Color(0xFFFFFF))

    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(member="The member to timeout", length="Amount of time to time them out for (format: #d#h#m#s)", reason="The reason for the timeout")
    @app_commands.command(name="timeout", description="Time out (mute) a member")
    async def timeout_command(self, interaction: discord.Interaction, member: discord.Member, length: app_commands.Transform[int, DurationTransformer], reason: str = None):
        if length >= 2419200:
            await interaction.response.send_message("Timeouts cannot be longer than 28 days!", ephemeral=True)
            return
        if await check_staff_target(interaction=interaction, user=member):
            return
            
        timeout_expiration = discord.utils.utcnow() + timedelta(seconds=length)
        timeout_expiration_str = format_dt(timeout_expiration)

        try:
            await member.timeout(timeout_expiration, reason=reason)
        except discord.Forbidden as forbidden_to_timeout_exception:
            await interaction.response.send_message(f"Failed to timeout member: {forbidden_to_timeout_exception}", ephemeral=True) 
            return

        information_embed = discord.Embed(
            title=f"You were given a timeout in {interaction.guild.name}!",
            description=f"Reason: {reason}\nUntil:{timeout_expiration_str}",
            color=discord.Color.red()
        )
        appeals_embed = await generate_appeal_embed(guild_id=interaction.guild.id)
        await send_dm_message(member=member, guild=interaction.guild, embeds=[information_embed, appeals_embed])
        await interaction.response.send_message(f"{member} ({member.id}) has been timed out until {timeout_expiration_str}.")
        await post_action_log(target=member, action=ActionType.Timeout, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=f"{reason}\nUntil:{timeout_expiration_str}", color=discord.Color.red(), author=interaction.user)
    
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(member="The member to untimeout", reason="The reason for the timeout removal")
    @app_commands.command(name="untimeout", description="Un time out (mute) a member")
    async def untimeout_command(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        try:
            await member.timeout(None) # removes the timeout
        except discord.Forbidden as forbidden_to_untimeout_exception:
            await interaction.response.send_message(f"Failed to untimeout member: {forbidden_to_untimeout_exception}", ephemeral=True) 
            return
        await interaction.response.send_message(f"{member} ({member.id}) is no longer timed out.")
        await post_action_log(target=member, action=ActionType.TimeoutRemoval, channel=await get_log_channel(guild=interaction.guild, log_channel_type=LogChannelType.ModLogs), reason=f"{reason}", color=discord.Color(0xFFFFFF), author=interaction.user)

async def setup(bot):
    await bot.add_cog(Mod(bot))
