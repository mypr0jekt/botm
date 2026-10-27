from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

LANGS = {
    "uz": "🇺🇿 O'zbek tilida",
    "ru": "🇷🇺 Rus tilida",
    "en": "🇬🇧 Ingliz tilida",
    "tr": "🇹🇷 Turk tilida",
}

PARTS_PER_PAGE = 20
MOVIES_PER_PAGE = 10


# ---------- Foydalanuvchi ----------

def sub_kb(channels, code: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"📢 {ch['title']}", url=ch["link"])
    b.button(text="✅ Tekshirish", callback_data=f"chk:{code}")
    b.adjust(1)
    return b.as_markup()


def parts_kb(code: int, total: int, current: int, page: int | None = None):
    """Ko'p qismli kino uchun qism tugmalari (20 tadan sahifalanadi)."""
    if total <= 1:
        return None
    pages = (total + PARTS_PER_PAGE - 1) // PARTS_PER_PAGE
    if page is None:
        page = (current - 1) // PARTS_PER_PAGE
    page = max(0, min(page, pages - 1))
    start = page * PARTS_PER_PAGE + 1
    end = min(total, start + PARTS_PER_PAGE - 1)

    b = InlineKeyboardBuilder()
    for n in range(start, end + 1):
        b.button(
            text=f"▶️ {n}" if n == current else str(n),
            callback_data=f"part:{code}:{n}",
        )
    b.adjust(5)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️", callback_data=f"pp:{code}:{current}:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️", callback_data=f"pp:{code}:{current}:{page + 1}"))
        b.row(*nav)
    return b.as_markup()


def search_kb(movies) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in movies:
        b.button(text=f"🎬 {m['title'][:40]} • {m['code']}", callback_data=f"movie:{m['code']}")
    b.adjust(1)
    return b.as_markup()


def watch_kb(bot_username: str, code: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 Tomosha qilish",
            url=f"https://t.me/{bot_username}?start={code}",
        )
    ]])


# ---------- Admin ----------

def admin_menu_kb(is_owner: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Kino qo'shish", callback_data="adm:add")
    b.button(text="🎞 Kinolar", callback_data="mv:list:0")
    b.button(text="📢 Majburiy kanallar", callback_data="adm:channels")
    b.button(text="📣 Post kanali", callback_data="adm:postch")
    b.button(text="📊 Statistika", callback_data="adm:stats")
    b.button(text="✉️ Xabar yuborish", callback_data="adm:bc")
    if is_owner:
        b.button(text="👥 Adminlar", callback_data="adm:admins")
    b.adjust(2)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")
    ]])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:menu")
    ]])


def lang_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in LANGS.items():
        b.button(text=label, callback_data=f"lang:{key}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel"))
    return b.as_markup()


def done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tugatish", callback_data="adm:done")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
    ])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Saqlash va kanalga joylash", callback_data="adm:save:1")],
        [InlineKeyboardButton(text="💾 Faqat saqlash", callback_data="adm:save:0")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
    ])


def channels_kb(channels) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"🗑 {ch['title'][:40]}", callback_data=f"ch:del:{ch['id']}")
    b.button(text="➕ Kanal qo'shish", callback_data="ch:add")
    b.button(text="⬅️ Admin panel", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def postch_kb(has_channel: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 O'zgartirish" if has_channel else "➕ Ulash", callback_data="pc:set")
    if has_channel:
        b.button(text="🗑 Olib tashlash", callback_data="pc:del")
    b.button(text="⬅️ Admin panel", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def movies_kb(movies, page: int, total: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in movies:
        b.button(text=f"{m['code']} • {m['title'][:35]}", callback_data=f"mv:open:{m['code']}")
    b.adjust(1)
    pages = max(1, (total + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"mv:list:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"mv:list:{page + 1}"))
    b.row(*nav)
    b.row(InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:menu"))
    return b.as_markup()


def movie_manage_kb(code: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga joylash", callback_data=f"mv:post:{code}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"mv:del:{code}")],
        [InlineKeyboardButton(text="⬅️ Ro'yxat", callback_data="mv:list:0")],
    ])


def movie_delete_confirm_kb(code: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"mv:delok:{code}"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data=f"mv:open:{code}"),
    ]])


def admins_kb(admin_ids: list[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for uid in admin_ids:
        b.button(text=f"🗑 {uid}", callback_data=f"ad:del:{uid}")
    b.button(text="➕ Admin qo'shish", callback_data="ad:add")
    b.button(text="⬅️ Admin panel", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yuborish", callback_data="bc:go"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel"),
    ]])
