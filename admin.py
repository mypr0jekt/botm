import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import subscription
from config import OWNER_ID
from utils import IsAdmin, esc, post_movie, resolve_chat, safe_edit

log = logging.getLogger(__name__)

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_tasks: set[asyncio.Task] = set()


class AddMovie(StatesGroup):
    title = State()
    language = State()
    poster = State()
    parts = State()
    confirm = State()


class AddChannel(StatesGroup):
    wait = State()


class SetPost(StatesGroup):
    wait = State()


class AddAdmin(StatesGroup):
    wait = State()


class Broadcast(StatesGroup):
    wait = State()
    confirm = State()


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ======================= Panel =======================

@router.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=kb.admin_menu_kb(is_owner(message.from_user.id)))


@router.callback_query(F.data.in_({"adm:menu", "adm:cancel"}))
async def admin_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await safe_edit(call, "🛠 <b>Admin panel</b>", kb.admin_menu_kb(is_owner(call.from_user.id)))


@router.callback_query(F.data == "adm:stats")
async def stats(call: CallbackQuery):
    s = await db.stats()
    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{s['users']}</b> (faol: {s['active']})\n"
        f"🆕 24 soatda qo'shilgan: <b>{s['new_24h']}</b>\n"
        f"🎬 Kinolar: <b>{s['movies']}</b>\n"
        f"🎞 Jami qismlar: <b>{s['parts']}</b>\n"
        f"👁 Ko'rishlar: <b>{s['views']}</b>"
    )
    await call.answer()
    await safe_edit(call, text, kb.back_kb())


# ======================= Kino qo'shish =======================

@router.callback_query(F.data == "adm:add")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddMovie.title)
    await call.answer()
    await safe_edit(call, "🎬 Kino nomini yuboring:", kb.cancel_kb())


@router.message(AddMovie.title, F.text)
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip()[:200])
    await state.set_state(AddMovie.language)
    await message.answer("🌐 Kino tilini tanlang yoki matn bilan yozing:", reply_markup=kb.lang_kb())


async def _ask_poster(target: Message, state: FSMContext, language: str):
    await state.update_data(language=language)
    await state.set_state(AddMovie.poster)
    await target.answer(
        "🖼 Kanalga joylanadigan <b>rasm</b> yoki <b>video</b> (treyler) yuboring:",
        reply_markup=kb.cancel_kb(),
    )


@router.callback_query(AddMovie.language, F.data.startswith("lang:"))
async def add_lang_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _ask_poster(call.message, state, kb.LANGS[call.data.split(":")[1]].split(" ", 1)[1])


@router.message(AddMovie.language, F.text)
async def add_lang_text(message: Message, state: FSMContext):
    await _ask_poster(message, state, message.text.strip()[:50])


@router.message(AddMovie.poster, F.photo | F.video)
async def add_poster(message: Message, state: FSMContext):
    if message.photo:
        fid, ftype = message.photo[-1].file_id, "photo"
    else:
        fid, ftype = message.video.file_id, "video"
    await state.update_data(poster_id=fid, poster_type=ftype, parts=[])
    await state.set_state(AddMovie.parts)
    await message.answer(
        "🎞 Endi kino videolarini yuboring.\n\n"
        "• Bitta kino bo'lsa — bitta video\n"
        "• Ko'p qismli bo'lsa — 1-qism, 2-qism... tartibida ketma-ket yuboring\n\n"
        "Hammasi yuborilgach «✅ Tugatish» tugmasini bosing.",
        reply_markup=kb.done_kb(),
    )


@router.message(AddMovie.poster)
async def poster_wrong(message: Message):
    await message.answer("❗ Rasm yoki video yuboring.", reply_markup=kb.cancel_kb())


@router.message(AddMovie.parts, F.video | F.document)
async def add_part(message: Message, state: FSMContext):
    data = await state.get_data()
    parts = data.get("parts", [])
    if message.video:
        parts.append([message.video.file_id, "video"])
    else:
        parts.append([message.document.file_id, "document"])
    await state.update_data(parts=parts)
    await message.answer(
        f"✅ {len(parts)}-qism qabul qilindi. Yana qism yuboring yoki «Tugatish» ni bosing.",
        reply_markup=kb.done_kb(),
    )


@router.message(AddMovie.parts)
async def part_wrong(message: Message):
    await message.answer("❗ Video yuboring yoki «Tugatish» ni bosing.", reply_markup=kb.done_kb())


@router.callback_query(AddMovie.parts, F.data == "adm:done")
async def add_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    parts = data.get("parts", [])
    if not parts:
        await call.answer("Kamida 1 ta video yuboring!", show_alert=True)
        return
    await state.set_state(AddMovie.confirm)
    await call.answer()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass
    await call.message.answer(
        "📋 <b>Tekshiring:</b>\n\n"
        f"🎬 Nomi: <b>{esc(data['title'])}</b>\n"
        f"🌐 Til: {esc(data['language'])}\n"
        f"🎞 Qismlar soni: <b>{len(parts)}</b>\n\n"
        "Saqlaysizmi?",
        reply_markup=kb.confirm_kb(),
    )


@router.callback_query(AddMovie.confirm, F.data.startswith("adm:save:"))
async def add_save(call: CallbackQuery, state: FSMContext, bot: Bot):
    do_post = call.data.endswith(":1")
    data = await state.get_data()
    await state.clear()
    code = await db.add_movie(
        data["title"], data["language"], data["poster_id"], data["poster_type"],
        [tuple(p) for p in data["parts"]],
    )
    text = f"✅ Kino saqlandi!\n🔑 Kod: <code>{code}</code>"
    if do_post:
        ok, err = await post_movie(bot, code)
        text += "\n📢 Kanalga joylandi." if ok else f"\n⚠️ Kanalga joylab bo'lmadi: {esc(err)}"
    await call.answer()
    await safe_edit(call, text, kb.admin_menu_kb(is_owner(call.from_user.id)))


# ======================= Kinolar ro'yxati =======================

@router.callback_query(F.data.startswith("mv:list:"))
async def movies_list(call: CallbackQuery):
    page = int(call.data.split(":")[2])
    total = await db.count_movies()
    movies = await db.list_movies(page * kb.MOVIES_PER_PAGE, kb.MOVIES_PER_PAGE)
    await call.answer()
    if not total:
        await safe_edit(call, "🎞 Hozircha kinolar yo'q.", kb.back_kb())
        return
    await safe_edit(call, f"🎞 <b>Kinolar</b> (jami: {total})", kb.movies_kb(movies, page, total))


@router.callback_query(F.data.startswith("mv:open:"))
async def movie_open(call: CallbackQuery):
    code = int(call.data.split(":")[2])
    movie = await db.get_movie(code)
    await call.answer()
    if not movie:
        await safe_edit(call, "❌ Kino topilmadi.", kb.back_kb())
        return
    total = await db.count_parts(code)
    text = (
        f"🎬 <b>{esc(movie['title'])}</b>\n"
        f"🌐 Til: {esc(movie['language'])}\n"
        f"🎞 Qismlar: {total}\n"
        f"👁 Ko'rishlar: {movie['views']}\n"
        f"🔑 Kod: <code>{code}</code>"
    )
    await safe_edit(call, text, kb.movie_manage_kb(code))


@router.callback_query(F.data.startswith("mv:post:"))
async def movie_post(call: CallbackQuery, bot: Bot):
    code = int(call.data.split(":")[2])
    ok, err = await post_movie(bot, code)
    if ok:
        await call.answer("📢 Kanalga joylandi!", show_alert=True)
    else:
        await call.answer(f"⚠️ {err}"[:190], show_alert=True)


@router.callback_query(F.data.startswith("mv:del:"))
async def movie_del(call: CallbackQuery):
    code = int(call.data.split(":")[2])
    await call.answer()
    await safe_edit(call, f"🗑 <code>{code}</code> kodli kinoni o'chirasizmi?", kb.movie_delete_confirm_kb(code))


@router.callback_query(F.data.startswith("mv:delok:"))
async def movie_delok(call: CallbackQuery):
    await db.delete_movie(int(call.data.split(":")[2]))
    await call.answer("🗑 O'chirildi")
    await safe_edit(call, "🗑 Kino o'chirildi.", kb.back_kb())


# ======================= Majburiy kanallar =======================

async def _channels_text() -> tuple[str, list]:
    chans = await db.list_channels()
    lines = [f"{i}. {esc(c['title'])}" for i, c in enumerate(chans, 1)]
    text = (
        "📢 <b>Majburiy obuna kanallari</b>\n\n"
        + ("\n".join(lines) if lines else "Hozircha kanal yo'q.")
        + "\n\n⚠️ Bot har bir kanalda <b>admin</b> bo'lishi shart (bot o'zini admin qila olmaydi — "
        "kanalga o'zingiz qo'shing).\n🗑 — kanalni olib tashlash."
    )
    return text, chans


@router.callback_query(F.data == "adm:channels")
async def channels_menu(call: CallbackQuery):
    text, chans = await _channels_text()
    await call.answer()
    await safe_edit(call, text, kb.channels_kb(chans))


@router.callback_query(F.data == "ch:add")
async def channel_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.wait)
    await call.answer()
    await safe_edit(
        call,
        "➕ Kanalni yuboring:\n• @username yoki t.me havolasi\n• kanal ID (-100...)\n"
        "• yoki kanaldan biror xabarni forward qiling\n\n"
        "Bot avval kanalga admin qilingan bo'lishi kerak.",
        kb.cancel_kb(),
    )


@router.message(AddChannel.wait)
async def channel_add_msg(message: Message, state: FSMContext, bot: Bot):
    chat, link, err = await resolve_chat(bot, message, need_link=True)
    if err:
        await message.answer(err, reply_markup=kb.cancel_kb())
        return
    await db.add_channel(chat.id, chat.title or str(chat.id), link)
    subscription.clear_cache()
    await state.clear()
    text, chans = await _channels_text()
    await message.answer(f"✅ <b>{esc(chat.title)}</b> qo'shildi.\n\n{text}", reply_markup=kb.channels_kb(chans))


@router.callback_query(F.data.startswith("ch:del:"))
async def channel_del(call: CallbackQuery):
    await db.del_channel(int(call.data.split(":")[2]))
    subscription.clear_cache()
    text, chans = await _channels_text()
    await call.answer("🗑 Olib tashlandi")
    await safe_edit(call, text, kb.channels_kb(chans))


# ======================= Post kanali =======================

async def _postch_text(bot: Bot) -> tuple[str, bool]:
    ch = await db.get_setting("post_channel")
    if not ch:
        return "📣 <b>Post kanali</b>\n\nHozircha ulanmagan.", False
    try:
        title = (await bot.get_chat(int(ch))).title
    except TelegramAPIError:
        title = ch
    return f"📣 <b>Post kanali</b>\n\nUlangan: <b>{esc(title)}</b>", True


@router.callback_query(F.data == "adm:postch")
async def postch_menu(call: CallbackQuery, bot: Bot):
    text, has = await _postch_text(bot)
    await call.answer()
    await safe_edit(call, text, kb.postch_kb(has))


@router.callback_query(F.data == "pc:set")
async def postch_set(call: CallbackQuery, state: FSMContext):
    await state.set_state(SetPost.wait)
    await call.answer()
    await safe_edit(
        call,
        "📣 Post tashlanadigan kanalni yuboring (@username, havola, ID yoki forward).\n"
        "Bot kanalda admin bo'lib, xabar yuborish huquqiga ega bo'lishi kerak.",
        kb.cancel_kb(),
    )


@router.message(SetPost.wait)
async def postch_msg(message: Message, state: FSMContext, bot: Bot):
    chat, _, err = await resolve_chat(bot, message, need_link=False)
    if err:
        await message.answer(err, reply_markup=kb.cancel_kb())
        return
    await db.set_setting("post_channel", str(chat.id))
    await state.clear()
    await message.answer(f"✅ Post kanali ulandi: <b>{esc(chat.title)}</b>", reply_markup=kb.back_kb())


@router.callback_query(F.data == "pc:del")
async def postch_del(call: CallbackQuery, bot: Bot):
    await db.set_setting("post_channel", None)
    text, has = await _postch_text(bot)
    await call.answer("🗑 Olib tashlandi")
    await safe_edit(call, text, kb.postch_kb(has))


# ======================= Adminlar (faqat owner) =======================

@router.callback_query(F.data == "adm:admins")
async def admins_menu(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("Faqat owner uchun", show_alert=True)
        return
    ids = db.list_admins()
    text = "👥 <b>Adminlar</b>\n\n" + ("\n".join(f"• <code>{i}</code>" for i in ids) if ids else "Qo'shimcha adminlar yo'q.")
    await call.answer()
    await safe_edit(call, text, kb.admins_kb(ids))


@router.callback_query(F.data == "ad:add")
async def admin_add(call: CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer("Faqat owner uchun", show_alert=True)
        return
    await state.set_state(AddAdmin.wait)
    await call.answer()
    await safe_edit(call, "➕ Yangi adminning Telegram ID raqamini yuboring:", kb.cancel_kb())


@router.message(AddAdmin.wait, F.text)
async def admin_add_msg(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❗ Faqat raqamli ID yuboring.", reply_markup=kb.cancel_kb())
        return
    await db.add_admin(int(message.text.strip()))
    await state.clear()
    ids = db.list_admins()
    await message.answer("✅ Admin qo'shildi.", reply_markup=kb.admins_kb(ids))


@router.callback_query(F.data.startswith("ad:del:"))
async def admin_del(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("Faqat owner uchun", show_alert=True)
        return
    await db.del_admin(int(call.data.split(":")[2]))
    ids = db.list_admins()
    await call.answer("🗑 Olib tashlandi")
    await safe_edit(call, "👥 <b>Adminlar</b>", kb.admins_kb(ids))


# ======================= Xabar yuborish =======================

@router.callback_query(F.data == "adm:bc")
async def bc_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.wait)
    await call.answer()
    await safe_edit(
        call,
        "✉️ Hamma foydalanuvchilarga yuboriladigan xabarni yuboring "
        "(matn, rasm, video — istalgan turi).",
        kb.cancel_kb(),
    )


@router.message(Broadcast.wait)
async def bc_msg(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(Broadcast.confirm)
    await message.answer("Shu xabar hammaga yuborilsinmi?", reply_markup=kb.broadcast_confirm_kb())


@router.callback_query(Broadcast.confirm, F.data == "bc:go")
async def bc_go(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await call.answer("Yuborish boshlandi")
    await safe_edit(call, "⏳ Xabar yuborilmoqda... Tugagach hisobot keladi.")
    task = asyncio.create_task(
        _run_broadcast(bot, data["chat_id"], data["message_id"], call.message.chat.id)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_broadcast(bot: Bot, from_chat: int, msg_id: int, report_chat: int) -> None:
    ok = fail = blocked = 0
    for uid in await db.active_user_ids():
        try:
            try:
                await bot.copy_message(uid, from_chat, msg_id)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                await bot.copy_message(uid, from_chat, msg_id)
            ok += 1
        except TelegramForbiddenError:
            blocked += 1
            await db.set_inactive(uid)
        except TelegramAPIError:
            fail += 1
        await asyncio.sleep(0.04)  # ~25 xabar/soniya
    try:
        await bot.send_message(
            report_chat,
            f"✅ Xabar yuborish tugadi\n\n📨 Yuborildi: {ok}\n🚫 Botni bloklagan: {blocked}\n⚠️ Xato: {fail}",
            reply_markup=kb.back_kb(),
        )
    except TelegramAPIError:
        log.exception("Hisobotni yuborib bo'lmadi")
