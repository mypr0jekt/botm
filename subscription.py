import logging

from aiogram import Bot

import database as db

log = logging.getLogger(__name__)


async def get_unsubscribed(bot: Bot, user_id: int):
    """Foydalanuvchi a'zo bo'lmagan majburiy kanallar ro'yxati."""
    missing = []
    for ch in await db.list_sub_channels():
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:
            # Bot kanalda admin emas yoki kanal topilmadi — tekshirib bo'lmaydi, o'tkazib yuboramiz
            log.warning("Obunani tekshirib bo'lmadi (%s): %s", ch["chat_id"], e)
    return missing
