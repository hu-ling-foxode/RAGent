from discord_bot import bot
import settings

def run():
    bot.run(settings.DISCORD_API_SECRET, root_logger=True)

if __name__ == "__main__":
  run()