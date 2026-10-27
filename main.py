import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

import admin
import database as db
import user
from config import BOT_TOKEN
from utils import ThrottleMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    await db.init()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # SimpleEventIsolation: admin bir vaqtda ko'p video yuborganda holat buzilmasligi uchun
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())

    throttle = ThrottleMiddleware(rate=0.6)
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)

    # Admin router birinchi: FSM holatlari foydalanuvchi handlerlaridan oldin ishlaydi
    dp.include_router(admin.router)
    dp.include_router(user.router)

    me = await bot.get_me()
    logging.info("Bot ishga tushdi: @%s", me.username)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
