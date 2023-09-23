import asyncio
import discord
import cmds
import settings

intents = discord.intents(
    GUILD_MESSAGES=True,
    GUILD_VOICE_STATES=True,
    DIRECT_MESSAGES=True,
    GUILD_MESSAGE_REACTIONS=True,
)
TOKEN = settings.BOT_KEY
bot = discord.Bot(cmd_prefix=".", token=TOKEN, intents=intents)


async def main():
    await cmds.update_prefix_cache(bot)
    await bot.start()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait([main()]))
