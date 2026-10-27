from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def subscribe_kb(channels, code: str = "") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["link"])] for ch in channels]
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"check:{code}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def watch_kb(bot_username: str, code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Tomosha qilish",
                    url=f"https://t.me/{bot_username}?start={code}",
                )
            ]
        ]
    )
