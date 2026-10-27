import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
DB_PATH = os.getenv("DB_PATH", "kino.db")
# Obuna tekshiruvi natijasi necha soniya eslab qolinadi (API yukini kamaytiradi)
SUB_CACHE_SECONDS = int(os.getenv("SUB_CACHE_SECONDS", "300"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN .env faylida ko'rsatilmagan")
if not OWNER_ID:
    raise SystemExit("OWNER_ID .env faylida ko'rsatilmagan")
