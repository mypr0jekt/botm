import html
import re
import time

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

import database as db
from keyboards import watch_kb


def esc(text: str | None) -> str:
    return html.escape(text or "")


# ---------- Filtr va middleware ----------

class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and db.is_admin(user.id))


class ThrottleMiddleware(BaseMiddleware):
    """Oddiy foydalanuvchilarni spamdan himoya qiladi (adminlarga tegmaydi)."""

    def __init__(self, rate: float = 0.6):
        self.rate = rate
        self._last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not db.is_admin(user.id):
            now = time.monotonic()
            if now - self._last.get(user.id, 0.0) < self.rate:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except TelegramAPIError:
                        pass
                return None
            self._last[user.id] = now
            if len(self._last) > 50_000:
                self._last.clear()
        return await handler(event, data)


# ---------- Yordamchi funksiyalar ----------

async def safe_edit(call: CallbackQuery, text: str, kb=None) -> None:
    """Xabarni tahrirlaydi; imkoni bo'lmasa (masalan media xabar) yangisini yuboradi."""
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return
        await call.message.answer(text, reply_markup=kb)


def parse_chat_ref(text: str):
    """@username, t.me havolasi yoki -100... ID ni ajratib oladi."""
    t = (text or "").strip()
    m = re.search(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?$", t)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"@[A-Za-z0-9_]{4,}", t):
        return t
    if re.fullmatch(r"-?\d{5,}", t):
        return int(t)
    return None


async def resolve_chat(bot: Bot, message: Message, need_link: bool):
    """
    Admin yuborgan kanalni aniqlaydi va botning o'sha kanalda adminligini tekshiradi.
    Qaytaradi: (chat, link, xato_matni)
    """
    ref = None
    fo = message.forward_origin
    if fo is not None and getattr(fo, "type", None) == "channel":
        ref = fo.chat.id
    elif message.text:
        ref = parse_chat_ref(message.text)
    if ref is None:
        return None, None, (
            "❌ Kanalni aniqlab bo'lmadi.\n"
            "@username, t.me havolasi, kanal ID (-100...) yuboring yoki kanaldan "
            "biror xabarni forward qiling."
        )
    try:
        chat = await bot.get_chat(ref)
    except TelegramAPIError:
        return None, None, "❌ Kanal topilmadi. Botni avval kanalga admin qilib qo'shing."
    if chat.type not in ("channel", "supergroup"):
        return None, None, "❌ Bu kanal emas. Kanal yoki guruh yuboring."
    try:
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError:
        return None, None, "❌ Bot bu kanalda yo'q. Avval botni kanalga admin qiling."
    if me.status not in ("administrator", "creator"):
        return None, None, "❌ Bot bu kanalda admin emas. Avval botni kanalga admin qiling."
    if not need_link and chat.type == "channel" and me.status == "administrator":
        if getattr(me, "can_post_messages", True) is False:
            return None, None, "❌ Botda kanalga xabar yuborish huquqi yo'q. Huquqni yoqing."
    link = None
    if need_link:
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            try:
                link = (await bot.create_chat_invite_link(chat.id)).invite_link
            except TelegramAPIError:
                return None, None, (
                    "❌ Maxfiy kanal uchun havola yaratib bo'lmadi. "
                    "Botga «Taklif havolalari» huquqini bering."
                )
    return chat, link, None


def movie_caption(movie, total_parts: int) -> str:
    lines = [
        f"🎬 <b>{esc(movie['title'])}</b>",
        f"🌐 Til: {esc(movie['language'])}",
    ]
    if total_parts > 1:
        lines.append(f"🎞 Qismlar: {total_parts} ta")
    lines.append(f"🔑 Kod: <code>{movie['code']}</code>")
    lines.append("\n📥 Ko'rish uchun pastdagi tugmani bosing yoki botga kodni yuboring.")
    return "\n".join(lines)


async def post_movie(bot: Bot, code: int) -> tuple[bool, str]:
    """Kinoni post kanaliga rasm/video + «Tomosha qilish» tugmasi bilan joylaydi."""
    channel = await db.get_setting("post_channel")
    if not channel:
        return False, "Post kanali ulanmagan"
    movie = await db.get_movie(code)
    if not movie:
        return False, "Kino topilmadi"
    total = await db.count_parts(code)
    caption = movie_caption(movie, total)
    kb = watch_kb((await bot.me()).username, code)
    try:
        if movie["poster_type"] == "photo":
            await bot.send_photo(int(channel), movie["poster_id"], caption=caption, reply_markup=kb)
        else:
            await bot.send_video(int(channel), movie["poster_id"], caption=caption, reply_markup=kb)
    except TelegramAPIError as e:
        return False, str(e)
    return True, ""
