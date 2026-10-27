from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.types import CallbackQuery, Message, User

import database as db
from keyboards import parts_kb, search_kb, sub_kb
from subscription import get_missing
from utils import esc

router = Router()

WELCOME = (
    "👋 Assalomu alaykum, <b>{name}</b>!\n\n"
    "🎬 Kino botiga xush kelibsiz.\n\n"
    "🔑 Kinoni ko'rish uchun <b>kino kodini</b> yuboring yoki "
    "<b>kino nomini</b> yozib qidiring."
)
SUB_TEXT = "📢 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, so'ng «✅ Tekshirish» tugmasini bosing:"


async def send_part(bot: Bot, chat_id: int, code: int, part_no: int) -> bool:
    movie = await db.get_movie(code)
    part = await db.get_part(code, part_no) if movie else None
    if not movie or not part:
        return False
    total = await db.count_parts(code)
    caption = f"🎬 <b>{esc(movie['title'])}</b>"
    if total > 1:
        caption += f"\n🎞 {part_no}-qism / {total}"
    caption += f"\n🌐 {esc(movie['language'])}\n🔑 Kod: <code>{code}</code>"
    kb = parts_kb(code, total, part_no)
    try:
        if part["file_type"] == "video":
            await bot.send_video(chat_id, part["file_id"], caption=caption,
                                 reply_markup=kb, supports_streaming=True)
        else:
            await bot.send_document(chat_id, part["file_id"], caption=caption, reply_markup=kb)
    except TelegramAPIError:
        return False
    if part_no == 1:
        await db.inc_views(code)
    return True


async def deliver(bot: Bot, user: User, code: int) -> None:
    """Obunani tekshirib, kinoning 1-qismini yuboradi."""
    missing = await get_missing(bot, user.id)
    if missing:
        await bot.send_message(user.id, SUB_TEXT, reply_markup=sub_kb(missing, code))
        return
    if not await send_part(bot, user.id, code, 1):
        await bot.send_message(user.id, "❌ Bunday kodli kino topilmadi.")


async def welcome(bot: Bot, user: User) -> None:
    missing = await get_missing(bot, user.id)
    if missing:
        await bot.send_message(user.id, SUB_TEXT, reply_markup=sub_kb(missing, 0))
        return
    await bot.send_message(user.id, WELCOME.format(name=esc(user.full_name)))


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot):
    u = message.from_user
    await db.add_user(u.id, u.full_name, u.username)
    arg = (command.args or "").strip()
    if arg.isdigit():
        await deliver(bot, u, int(arg))
    else:
        await welcome(bot, u)


@router.message(StateFilter(None), F.text.regexp(r"^\d{1,9}$"))
async def by_code(message: Message, bot: Bot):
    u = message.from_user
    await db.add_user(u.id, u.full_name, u.username)
    await deliver(bot, u, int(message.text))


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def by_title(message: Message, bot: Bot):
    u = message.from_user
    await db.add_user(u.id, u.full_name, u.username)
    q = message.text.strip()
    if len(q) < 2:
        await message.answer("🔎 Kamida 2 ta harf yozing yoki kino kodini yuboring.")
        return
    movies = await db.search_movies(q)
    if not movies:
        await message.answer("❌ Hech narsa topilmadi. Kino kodini yoki to'g'ri nomini yuboring.")
        return
    await message.answer("🔎 Topilgan kinolar:", reply_markup=search_kb(movies))


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("movie:"))
async def pick_movie(call: CallbackQuery, bot: Bot):
    await call.answer()
    await deliver(bot, call.from_user, int(call.data.split(":")[1]))


@router.callback_query(F.data.startswith("chk:"))
async def check_sub(call: CallbackQuery, bot: Bot):
    code = int(call.data.split(":")[1])
    missing = await get_missing(bot, call.from_user.id, force=True)
    if missing:
        await call.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=sub_kb(missing, code))
        return
    await call.answer("✅ Rahmat!")
    with suppress(TelegramAPIError):
        await call.message.delete()
    if code:
        await deliver(bot, call.from_user, code)
    else:
        await bot.send_message(call.from_user.id, WELCOME.format(name=esc(call.from_user.full_name)))


@router.callback_query(F.data.startswith("part:"))
async def pick_part(call: CallbackQuery, bot: Bot):
    _, code, no = call.data.split(":")
    missing = await get_missing(bot, call.from_user.id)
    if missing:
        await call.answer()
        await bot.send_message(call.from_user.id, SUB_TEXT, reply_markup=sub_kb(missing, int(code)))
        return
    await call.answer()
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)
    if not await send_part(bot, call.from_user.id, int(code), int(no)):
        await bot.send_message(call.from_user.id, "❌ Qism topilmadi.")


@router.callback_query(F.data.startswith("pp:"))
async def parts_page(call: CallbackQuery):
    _, code, current, page = call.data.split(":")
    total = await db.count_parts(int(code))
    await call.answer()
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=parts_kb(int(code), total, int(current), int(page))
        )
