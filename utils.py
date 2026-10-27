import html

from aiogram import Bot
from aiogram.types import Message

import database as db


def esc(text: str) -> str:
    return html.escape(text or "")


async def is_admin(user_id: int) -> bool:
    from config import OWNER_ID

    return user_id == OWNER_ID or await db.is_admin_db(user_id)


async def send_movie(bot: Bot, chat_id: int, movie) -> None:
    parts = await db.get_parts(movie["id"])
    total = len(parts)
    for p in parts:
        if total > 1:
            caption = f"🎬 <b>{esc(movie['title'])}</b>\n📺 {p['part_no']}-qism / {total}\n🌐 {esc(movie['language'])}"
        else:
            caption = f"🎬 <b>{esc(movie['title'])}</b>\n🌐 {esc(movie['language'])}"
        if p["file_type"] == "video":
            await bot.send_video(chat_id, p["file_id"], caption=caption)
        else:
            await bot.send_document(chat_id, p["file_id"], caption=caption)


def extract_file(message: Message):
    """(file_id, file_type) yoki None."""
    if message.video:
        return message.video.file_id, "video"
    if message.document:
        return message.document.file_id, "document"
    return None
