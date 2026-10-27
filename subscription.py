import asyncio
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import database as db
from config import SUB_CACHE_SECONDS

# user_id -> obuna tekshiruvi "o'tgan" deb hisoblanadigan muddat tugash vaqti
_ok_cache: dict[int, float] = {}


def clear_cache() -> None:
    _ok_cache.clear()


async def _is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        # Bot kanaldan chiqarilgan yoki kanal o'chgan bo'lsa, foydalanuvchini bloklamaymiz
        return True
    if m.status in ("member", "administrator", "creator"):
        return True
    return m.status == "restricted" and bool(getattr(m, "is_member", False))


async def get_missing(bot: Bot, user_id: int, force: bool = False):
    """Foydalanuvchi a'zo bo'lmagan majburiy kanallar ro'yxatini qaytaradi."""
    if db.is_admin(user_id):
        return []
    channels = await db.list_channels()
    if not channels:
        return []
    if not force:
        exp = _ok_cache.get(user_id)
        if exp and exp > time.time():
            return []
    results = await asyncio.gather(
        *(_is_member(bot, c["chat_id"], user_id) for c in channels)
    )
    missing = [c for c, ok in zip(channels, results) if not ok]
    if not missing:
        if len(_ok_cache) > 100_000:
            _ok_cache.clear()
        _ok_cache[user_id] = time.time() + SUB_CACHE_SECONDS
    else:
        _ok_cache.pop(user_id, None)
    return missing
