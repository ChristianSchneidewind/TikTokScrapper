# backend/config.py
import os
import logging
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))  # /.../backend
ROOT_DIR = os.path.dirname(BACKEND_DIR)                   # Projekt-Root

COOKIE_FILE = os.path.join(ROOT_DIR, "tiktok_cookies.json")
URLS_FILE   = os.path.join(ROOT_DIR, "video_urls.txt")
TIKTOK_URL  = "https://www.tiktok.com/"
LONG_TIMEOUT = 60

# Screenshots
SCREENSHOTS_DIR = os.path.join(ROOT_DIR, "screenshots")

# Telegram (aus .env)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")