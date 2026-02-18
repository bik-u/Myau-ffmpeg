import asyncio
import discord
import settings
import cmds 

intents = discord.intents(
    GUILD_MESSAGES=True,
    GUILD_VOICE_STATES=True,
    DIRECT_MESSAGES=True,
    GUILD_MESSAGE_REACTIONS=True,
)
TOKEN = settings.BOT_KEY
bot = discord.Bot(cmd_prefix=".", token=TOKEN, intents=intents)


async def main():
    await bot.start()


if __name__ == "__main__":
    while True:
        asyncio.run(main())
