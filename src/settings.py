import os
from dotenv import load_dotenv


load_dotenv("run.env")


BOT_KEY = os.getenv("BOT_KEY")
FFMPEG_LOCATION = os.getenv("FFMPEG_LOCATION")
YT_DL_LOCATION = os.getenv("YT_DL_LOCATION")
COOKIES = os.getenv("COOKIES_LOCATIOn")
