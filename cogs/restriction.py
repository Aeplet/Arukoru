import discord
from discord import app_commands
from discord.ext import commands

from utils.enums import LogChannelType, ActionType
from utils.helpers import check_guild_restriction_exists_by_name, get_all_restriction_names_for_guild, get_all_user_restrictions_for_guild, check_guild_restriction_exists_by_role, post_action_log, get_guild_restriction_type_id_by_name, get_role_for_restriction_type_by_restriction_type_id, get_role_for_restriction_type_by_name, user_has_restriction
from utils.channels import get_log_channel
import utils.database as database

@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True) # Manage roles seems like the best default permission here. Individual servers can configure it on a per server basis anyways
# @app_commands.checks.bot_has_permissions(manage_roles=True) This is not used because this checks for Manage Roles overrides in channels

# This cog is a damn mess. TODO: PLEASE REWORK IT.
class Restriction(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        user_restrictions = await get_all_user_restrictions_for_guild(user_id=member.id, guild_id=member.guild.id)
        for count, (restriction_id, timestamp, issuer_id, reason, user_id, restriction_type, guild_id) in enumerate(user_restrictions, start=1):
            if await user_has_restriction(user_id=member.id, guild_id=member.guild.id, restriction_type_id=restriction_type):
                role_object = await get_role_for_restriction_type_by_restriction_type_id(restriction_type_id=restriction_type, guild=member.guild)
                try:
                    await member.add_roles(role_object, reason=f"Restriction applied for reason {reason}")
                except discord.Forbidden:
                    pass
                    # todo: post a server log
                except discord.NotFound:
                    pass
                    # todo: same thing, post a server log

    # todo: don't grab it from the db every time. use discord.ext.tasks.
    async def restriction_name_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        restrictions = await get_all_restriction_names_for_guild(guild_id=interaction.guild.id)
        return [app_commands.Choice(name=name, value=name) for name in restrictions if current.casefold() in name.casefold()] # we need to return app_commands.Choice list

    @app_commands.describe(name="Name of the restriction", role="The role to apply when the restriction is applied")
    @app_commands.command(name="create", description="Create a restriction in this server.")
    async def create_restriction_command(self, interaction: discord.Interaction, name: str, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild # shortcut for this command, this command should be split into multiple functions but whatever for now :shrug: i do two basic checks that should be split into a function so...

        if role.managed:
            raise ValueError(f"{role.mention} is a role managed by a bot, therefore it cannot be assigned to members, and therefore it cannot be used for restrictions. Please use a different role.")
        if await check_guild_restriction_exists_by_role(role_id=role.id):
            raise ValueError(f"A restriction with the role {role.mention} already exists.")
        if await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name):
            raise ValueError(f"A restriction with the name {name} already exists in the server {guild.name}.")
        await database.execute("INSERT INTO guild_restrictions (guild_id, restriction_name, restriction_role_id) VALUES (?, ?, ?)", parameters=(guild.id, name, role.id,)) # all of the above is just for this mainly lol

        if await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name) and await check_guild_restriction_exists_by_role(role_id=role.id):
            await interaction.followup.send(f"Successfully added restriction with name {name} to server {guild.name}!", ephemeral=True)
            # BIG TODO: USE A SEPARATE LOG TYPE THAT IS MORE DETAILED. AND DON'T USE REASON. REASON IS ONLY A TEMPORARY SOLUTION.
            log_channel = await get_log_channel(guild=guild, log_channel_type=LogChannelType.ModLogs)
            await post_action_log(color=discord.Color.blue(), author=interaction.user, channel=log_channel, action=ActionType.AddedRestrictionToGuild, reason=f"Restriction Name: {name}\n Role: {role.mention}")
            return
        else:
            await interaction.followup.send(f"Failed to add restriction with name {name} to server {guild.name}.", ephemeral=True)
            return

    # I am worried someone will confuse this command for /restriction remove. Maybe add a confirm modal?
    @app_commands.describe(name="The restriction to delete")
    @app_commands.command(name="delete", description="Delete a restriction from this server, for everyone")
    @app_commands.autocomplete(name=restriction_name_autocomplete)
    async def delete_restriction_command(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild # shortcut for this command, this command should be split into multiple functions but whatever for now :shrug: i do two basic checks that should be split into a function so...
        if not await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name):
            raise ValueError(f"There is no restriction named {name} in {guild.name}.")

        await database.execute("DELETE FROM guild_restrictions WHERE guild_id = ? AND restriction_name = ?", parameters=(guild.id, name,))

        if not await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name):
            await interaction.followup.send(f"Successfully deleted restriction with name {name} in server {guild.name}!", ephemeral=True)
            # BIG TODO: USE A SEPARATE LOG TYPE THAT IS MORE DETAILED. AND DON'T USE REASON. REASON IS ONLY A TEMPORARY SOLUTION.
            log_channel = await get_log_channel(guild=guild, log_channel_type=LogChannelType.ModLogs)
            await post_action_log(color=discord.Color.blue(), author=interaction.user, channel=log_channel, action=ActionType.RemovedRestrictionFromGuild, reason=f"Restriction Name: {name}")
            return
        else:
            await interaction.followup.send(f"Failed to remove restriction with name {name} from server {guild.name}.", ephemeral=True)
            return

    # this needs a clean up too.
    @app_commands.describe(name="The name of the restriction to apply", user="The user to apply the restriction to", reason="The reason for applying the restriction")
    @app_commands.command(name="apply", description="Apply a restriction to a user")
    @app_commands.autocomplete(name=restriction_name_autocomplete)
    async def apply_restriction_command(self, interaction: discord.Interaction, name: str, user: discord.User, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        author = interaction.user
        if not guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("I do not have the Manage Roles permission in this server. This can be fixed by assigning me a role with the permission.", ephemeral=True)
            return

        if not await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name):
            raise ValueError(f"There is no restriction named {name} in {guild.name}.")

        role_object = await get_role_for_restriction_type_by_name(guild=guild, name=name)
        if role_object is None:
            raise ValueError(f"The role for the restriction {name} was deleted. Consider deleting this restriction.")
        if role_object >= guild.me.top_role:
            raise ValueError(f"I cannot assign {role_object.mention} to {user.mention}, as it is higher or equal to me in the role hierachy. Please fix this, and then try again.")
        if role_object.managed:
            raise ValueError(f"I cannot assign {role_object.mention} to {user.mention}, as it is a role managed by a bot. Please assign a different role to this restriction.")
        
        restriction_type_id = await get_guild_restriction_type_id_by_name(guild_id=guild.id, name=name)
        if await user_has_restriction(user_id=user.id, guild_id=guild.id, restriction_type_id=restriction_type_id):
            raise ValueError(f"{user.mention} already has a {name} restriction in {guild.name}!")
        
        await database.execute("INSERT INTO user_restrictions (issuer_id, user_id, restriction_type, guild_id, reason) VALUES (?, ?, ?, ?, ?)", parameters=(author.id, user.id, restriction_type_id, guild.id, reason))

        if not await user_has_restriction(user_id=user.id, guild_id=guild.id, restriction_type_id=restriction_type_id):
            await interaction.followup.send(f"Failed to apply restriction {name} to {user.mention}.", ephemeral=True)
            return

        # we need a member object to apply/remove a role.
        try:
            member = guild.get_member(user.id) or await guild.fetch_member(user.id)
            if member:
                await member.add_roles(role_object)
                await interaction.followup.send(f"Successfully applied restriction {name} to {user.mention}!", ephemeral=True)
        # log these for now at least
        except discord.Forbidden as e:
            await interaction.followup.send(f"I am missing permissions to apply that role.")
        except discord.NotFound as e:
            await interaction.followup.send(f"Restriction was applied, but {user.mention} is not in the server. They will receive the role the next time they join the server.")
        # BIG TODO: USE A SEPARATE LOG TYPE THAT IS MORE DETAILED. AND DON'T USE REASON. REASON IS ONLY A TEMPORARY SOLUTION.
        log_channel = await get_log_channel(guild=guild, log_channel_type=LogChannelType.ModLogs)
        await post_action_log(action=ActionType.ApplyRestrictionToUser, channel=log_channel, author=author, target=user, reason=f"Restriction Name: {name}\n Reason: {reason}")

    # this needs a clean up too.
    @app_commands.describe(name="The name of the restriction to remove", user="The user to remove the restriction from", reason="The reason for removing the restriction")
    @app_commands.command(name="remove", description="Remove a restriction to a user")
    @app_commands.autocomplete(name=restriction_name_autocomplete)
    async def remove_restriction_command(self, interaction: discord.Interaction, name: str, user: discord.User, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        author = interaction.user
        if not guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("I do not have the Manage Roles permission in this server. This can be fixed by assigning me a role with the permission.", ephemeral=True)
            return
    
        if not await check_guild_restriction_exists_by_name(guild_id=guild.id, name=name):
            raise ValueError(f"There is no restriction named {name} in {guild.name}.")

        role_object = await get_role_for_restriction_type_by_name(guild=guild, name=name)
        if role_object is None:
            raise ValueError(f"The role for the restriction {name} was deleted. Consider deleting this restriction.")
        if role_object >= guild.me.top_role:
            raise ValueError(f"I cannot remove {role_object.mention} from {user.mention}, as it is higher or equal to me in the role hierachy. Please fix this, and then try again.")
        if role_object.managed:
            raise ValueError(f"I cannot remove {role_object.mention} from {user.mention}, as it is a role managed by a bot. Please assign a different role to this restriction.")
            
        restriction_type_id = await get_guild_restriction_type_id_by_name(guild_id=guild.id, name=name)
        if not await user_has_restriction(user_id=user.id, guild_id=guild.id, restriction_type_id=restriction_type_id):
            raise ValueError(f"{user.mention} does not have a {name} restriction in {guild.name}!")
        
        await database.execute("DELETE FROM user_restrictions WHERE user_id = ? AND restriction_type = ? AND guild_id = ?", parameters=(user.id, restriction_type_id, guild.id,))
    
        if await user_has_restriction(user_id=user.id, guild_id=guild.id, restriction_type_id=restriction_type_id):
            await interaction.followup.send(f"Failed to remove restriction {name} from {user.mention}.", ephemeral=True)
            return
    
        # we need a member object to apply/remove a role.
        try:
            member = guild.get_member(user.id) or await guild.fetch_member(user.id)
            if member:
                await member.remove_roles(role_object)
                await interaction.followup.send(f"Successfully removed restriction {name} from {user.mention}!", ephemeral=True)
        # log these for now at least
        except discord.Forbidden as e:
            await interaction.followup.send(f"I am missing permissions to remove that role.")
        except discord.NotFound as e:
            await interaction.followup.send(f"Restriction was removed, but {user.mention} is not in the server. They will no longer automatically receive the role the next time they join the server.")
        # BIG TODO: USE A SEPARATE LOG TYPE THAT IS MORE DETAILED. AND DON'T USE REASON. REASON IS ONLY A TEMPORARY SOLUTION.
        log_channel = await get_log_channel(guild=guild, log_channel_type=LogChannelType.ModLogs)
        await post_action_log(action=ActionType.RemoveRestrictionFromUser, channel=log_channel, author=author, target=user, reason=f"Restriction Name: {name}\n Reason: {reason}")
        

async def setup(bot):
    await bot.add_cog(Restriction(bot))