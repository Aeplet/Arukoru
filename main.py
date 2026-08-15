# general lib imports
import asyncio
import traceback
import io
from datetime import datetime

import discord
from discord.app_commands.errors import CommandInvokeError, TransformerError, CheckFailure
from discord.ext import commands
from discord.utils import format_dt

from constants import TOKEN, BOT_ERROR_CHANNEL_ID, SERVER_LOGS_CHANNEL_ID, MOD_LOGS_CHANNEL_ID, MESSAGE_LOGS_CHANNEL_ID
from utils.enums import ServerAction, MessageLog
from utils.helpers import AppNotBotDeveloper, AppNotStaffCheck, post_message_log, post_server_log, handle_honeypot_action
from utils.database import init_database

discord.utils.setup_logging()

# We are no longer free to use discord.Intents.all() as we do not have a valid excuse for the Presence intent. We now have all intents except for it.
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)

class Bot(commands.Bot):
    async def setup_hook(self):
        self.server_logs_channel = (self.get_channel(SERVER_LOGS_CHANNEL_ID) or await self.fetch_channel(SERVER_LOGS_CHANNEL_ID))
        self.mod_logs_channel = (self.get_channel(MOD_LOGS_CHANNEL_ID) or await self.fetch_channel(MOD_LOGS_CHANNEL_ID))
        self.message_logs_channel = (self.get_channel(MESSAGE_LOGS_CHANNEL_ID) or await self.fetch_channel(MESSAGE_LOGS_CHANNEL_ID))

        # sync slash commands
        await self.tree.sync()
        print("Synced app commands successfully!")


bot = Bot(command_prefix=commands.when_mentioned, intents=intents, allowed_mentions=allowed_mentions)

cogs_list = [
    "cogs.extras",
    "cogs.mod",
    "cogs.dev",
    "cogs.restriction",
    "cogs.logs"
]

async def load_extensions():
    for cog in cogs_list:
        await bot.load_extension(cog)
        print(f"Successfully loaded {cog}!")

# events should eventually be moved to a listener cog.

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

@bot.event
async def on_member_join(member: discord.Member):
    await post_server_log(bot=bot, serverAction=ServerAction.Join, channel=bot.server_logs_channel, color=discord.Color.gold(), target=member, note=f"Created: {member.created_at} ({format_dt(member.created_at)}) ({format_dt(member.created_at, style='R')})")

@bot.event
async def on_member_remove(member: discord.Member):
    await post_server_log(bot=bot, serverAction=ServerAction.Leave, channel=bot.server_logs_channel, color=discord.Color.gold(), target=member, note=f"Created: {member.created_at} ({format_dt(member.created_at)}) ({format_dt(member.created_at, style='R')})")

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message: discord.Message):
    if isinstance(message.channel, discord.DMChannel):
        return
    if message.author.id == bot.user.id:
        return
    await post_message_log(bot=bot, messageLog=MessageLog.Delete, channel=bot.message_logs_channel, color=discord.Color.red(), message=message)

@bot.event
async def on_message_edit(old_message: discord.Message, new_message: discord.Message):
    if isinstance(old_message.channel, discord.DMChannel):
        return
    if old_message.author.id == bot.user.id:
        return
    if old_message.content == new_message.content:
        return
    await post_message_log(bot=bot, messageLog=MessageLog.Edit, channel=bot.message_logs_channel, color=discord.Color.blue(), message=old_message, new_message=new_message)

@bot.event
async def on_error(event, *args, **kwargs):
    channel = bot.get_channel(BOT_ERROR_CHANNEL_ID)
    error_text = traceback.format_exc()

    if channel:
        if len(error_text) <= 2000:
            await channel.send(f"Error in {event}\n```py\n{error_text}\n```")
        else:
            file = discord.File(io.BytesIO(error_text.encode("utf-8")), filename=f"{event}_traceback_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt")
            await channel.send(f"Error in {event}", file=file)
            
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, CommandInvokeError):
        error = error.original

    if isinstance(error, (AppNotBotDeveloper, AppNotStaffCheck, ValueError, TransformerError, CheckFailure)):
        await interaction.response.send_message(str(error), ephemeral=True)
        return

    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    # hacky formatting shit, damn
    embed = discord.Embed(title="Command Error", description=f"```py\n{tb[:4000]}\n```", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Command", value=f"`/{interaction.command.qualified_name if interaction.command else 'unknown'}`", inline=False)
    embed.add_field(name="User", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
    embed.add_field(name="Guild", value=f"{interaction.guild.name}\n`{interaction.guild.id}`" if interaction.guild else "DM", inline=True)
    embed.add_field(name="Channel", value=f"{interaction.channel.mention}\n`{interaction.channel.id}`" if interaction.channel else "DM", inline=True)
    embed.set_footer(text=type(error).__name__)

    channel = bot.get_channel(BOT_ERROR_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

    message = "An error has occurred. Please notify Aep (<@82870140068171776>) immediately."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

async def main():
    await init_database()
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

asyncio.run(main())