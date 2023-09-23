import os
from dotenv import load_dotenv

if os.getenv("TEST") == "TEST" :
    load_dotenv("test.env")
else:
    load_dotenv("run.env")


BOT_KEY = os.getenv("BOT_KEY")
