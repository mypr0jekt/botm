from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import subscribe_kb
from subscription import get_unsubscribed
from utils import esc, send_movie

router = Router()

SUB_TEXT = "❗️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, so'ng «Tekshirish» tugmasini bosing:"


async def deliver(bot: Bot, chat_id: int, user_id: int, code: str, reply_to: Message | None = None):
    """Obunani tekshiradi va kino yuboradi."""
    missing = await get_unsubscribed(bot, user_id)
    if missing:
        await bot.send_message(chat_id, SUB_TEXT, reply_markup=subscribe_kb(missing, code))
        return
    movie = await db.get_movie(code)
    if not movie:
        await bot.send_message(chat_id, "😔 Bu kod bo'yicha kino topilmadi.")
        return
    await send_movie(bot, chat_id, movie)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot):
    await db.add_user(message.from_user.id)
    code = (command.args or "").strip()
    if code:
        await deliver(bot, message.chat.id, message.from_user.id, code)
        return
    missing = await get_unsubscribed(bot, message.from_user.id)
    if missing:
        await message.answer(SUB_TEXT, reply_markup=subscribe_kb(missing))
        return
    await message.answer(
        f"👋 Salom, <b>{esc(message.from_user.full_name)}</b>!\n\n"
        "🎬 Kino kodini yuboring — men uni topib beraman."
    )


@router.callback_query(F.data.startswith("check:"))
async def check_sub(call: CallbackQuery, bot: Bot):
    code = call.data.split(":", 1)[1]
    missing = await get_unsubscribed(bot, call.from_user.id)
    if missing:
        await call.answer("Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
        return
    await call.answer("✅ Rahmat!")
    try:
        await call.message.delete()
    except Exception:
        pass
    if code:
        await deliver(bot, call.message.chat.id, call.from_user.id, code)
    else:
        await bot.send_message(call.message.chat.id, "🎬 Endi kino kodini yuboring.")


@router.message(F.text & ~F.text.startswith("/"))
async def by_code(message: Message, bot: Bot):
    await db.add_user(message.from_user.id)
    await deliver(bot, message.chat.id, message.from_user.id, message.text.strip())
