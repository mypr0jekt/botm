import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import database as db
from config import OWNER_ID
from keyboards import watch_kb
from utils import esc, extract_file, is_admin

router = Router()


class AddMovie(StatesGroup):
    title = State()
    language = State()
    code = State()
    parts = State()


async def _admin_only(message: Message) -> bool:
    return await is_admin(message.from_user.id)


router.message.filter(_admin_only)

HELP = (
    "🛠 <b>Admin buyruqlari</b>\n\n"
    "🎬 <b>Kinolar</b>\n"
    "/addmovie — yangi kino/serial qo'shish\n"
    "/movies — oxirgi kinolar ro'yxati\n"
    "/delmovie <code>KOD</code> — kinoni o'chirish\n\n"
    "📢 <b>Majburiy obuna</b>\n"
    "/addchannel <code>@kanal</code> yoki <code>-100...</code> [havola] — qo'shish\n"
    "/delchannel <code>@kanal</code> yoki <code>-100...</code> — o'chirish\n"
    "/channels — ro'yxat\n\n"
    "📮 <b>Post kanali</b>\n"
    "/setpost <code>@kanal</code> yoki <code>-100...</code> — kinolar tashlanadigan kanal\n"
    "/unsetpost — post kanalini o'chirish\n\n"
    "👥 /stats — statistika\n"
    "/broadcast — xabar tarqatish (xabarga reply qiling)\n"
    "/addadmin <code>ID</code>, /deladmin <code>ID</code>, /admins — adminlar (faqat egasi)\n\n"
    "ℹ️ Bot kanalda <b>admin</b> bo'lishi kerak (a'zolikni tekshirish va post tashlash uchun). "
    "Buni Telegram qoidasiga ko'ra botning o'zi qila olmaydi — kanalga bir marta qo'lda qo'shing."
)


@router.message(Command("admin", "help"))
async def admin_help(message: Message):
    await message.answer(HELP)


# ---------- kino qo'shish ----------
@router.message(Command("cancel"), StateFilter("*"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.")


@router.message(Command("addmovie"))
async def addmovie(message: Message, state: FSMContext):
    await state.set_state(AddMovie.title)
    await message.answer("🎬 Kino nomini yuboring:\n\n(bekor qilish: /cancel)")


@router.message(AddMovie.title, F.text)
async def am_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddMovie.language)
    await message.answer("🌐 Tilini yuboring (masalan: O'zbek tilida):")


@router.message(AddMovie.language, F.text)
async def am_language(message: Message, state: FSMContext):
    await state.update_data(language=message.text.strip())
    await state.set_state(AddMovie.code)
    suggested = await db.next_code()
    await message.answer(
        f"🔢 Kino kodini yuboring.\nAvtomatik kod uchun <code>{suggested}</code> ni yuboring yoki o'zingiz yozing:"
    )


@router.message(AddMovie.code, F.text)
async def am_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if " " in code or code.startswith("/"):
        await message.answer("Kodda bo'sh joy bo'lmasligi va / bilan boshlanmasligi kerak.")
        return
    if await db.code_exists(code):
        await message.answer("⚠️ Bu kod band. Boshqa kod yuboring:")
        return
    await state.update_data(code=code, parts=[])
    await state.set_state(AddMovie.parts)
    await message.answer(
        "📥 Endi video(lar)ni yuboring. Serial bo'lsa qismlarni tartib bilan birin-ketin yuboring.\n"
        "Tugagach /done yozing."
    )


@router.message(AddMovie.parts, Command("done"))
async def am_done(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    parts = data.get("parts", [])
    if not parts:
        await message.answer("Hech narsa yuborilmadi. Video yuboring yoki /cancel.")
        return
    await db.add_movie(data["code"], data["title"], data["language"], parts)
    await state.clear()
    await message.answer(
        f"✅ Saqlandi!\n🎬 {esc(data['title'])}\n🔢 Kod: <code>{esc(data['code'])}</code>\n📺 Qismlar: {len(parts)}"
    )
    await post_to_channel(bot, message, data, len(parts))


@router.message(AddMovie.parts)
async def am_part(message: Message, state: FSMContext):
    f = extract_file(message)
    if not f:
        await message.answer("Faqat video yoki fayl yuboring (tugatish: /done).")
        return
    data = await state.get_data()
    parts = data.get("parts", [])
    parts.append(f)
    await state.update_data(parts=parts)
    await message.answer(f"✅ {len(parts)}-qism qabul qilindi. Yana yuboring yoki /done.")


async def post_to_channel(bot: Bot, message: Message, data: dict, n_parts: int):
    chat = await db.get_setting("post_channel")
    if not chat:
        await message.answer("ℹ️ Post kanali o'rnatilmagan (/setpost), shuning uchun kanalga post tashlanmadi.")
        return
    me = await bot.get_me()
    text = (
        f"🎬 <b>{esc(data['title'])}</b>\n\n"
        f"🌐 Til: {esc(data['language'])}\n"
        f"🔢 Kod: <code>{esc(data['code'])}</code>"
    )
    if n_parts > 1:
        text += f"\n📺 Qismlar: {n_parts}"
    try:
        await bot.send_message(int(chat), text, reply_markup=watch_kb(me.username, data["code"]))
        await message.answer("📮 Kanalga post tashlandi.")
    except Exception as e:
        await message.answer(f"⚠️ Kanalga post tashlab bo'lmadi: {esc(str(e))}\nBot kanalda admin ekanini tekshiring.")


# ---------- kinolar ----------
@router.message(Command("movies"))
async def movies(message: Message):
    rows = await db.list_movies()
    if not rows:
        await message.answer("Hozircha kino yo'q.")
        return
    lines = [f"<code>{esc(r['code'])}</code> — {esc(r['title'])} ({esc(r['language'])}, {r['parts']} qism)" for r in rows]
    await message.answer("🎬 <b>Oxirgi kinolar:</b>\n\n" + "\n".join(lines))


@router.message(Command("delmovie"))
async def delmovie(message: Message, command: CommandObject):
    code = (command.args or "").strip()
    if not code:
        await message.answer("Foydalanish: /delmovie KOD")
        return
    ok = await db.delete_movie(code)
    await message.answer("🗑 O'chirildi." if ok else "Bunday kod topilmadi.")


# ---------- majburiy kanallar ----------
async def _resolve_chat(bot: Bot, ref: str):
    chat = await bot.get_chat(int(ref) if ref.lstrip("-").isdigit() else ref)
    return chat


@router.message(Command("addchannel"))
async def addchannel(message: Message, command: CommandObject, bot: Bot):
    args = (command.args or "").split()
    if not args:
        await message.answer("Foydalanish: /addchannel @kanal  yoki  /addchannel -100123... https://t.me/+havola")
        return
    try:
        chat = await _resolve_chat(bot, args[0])
    except Exception as e:
        await message.answer(f"⚠️ Kanal topilmadi: {esc(str(e))}")
        return
    link = args[1] if len(args) > 1 else (f"https://t.me/{chat.username}" if chat.username else None)
    if not link:
        await message.answer("Yopiq kanal uchun taklif havolasini ham yozing: /addchannel -100123... https://t.me/+xxxx")
        return
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in ("administrator", "creator"):
            await message.answer("⚠️ Bot bu kanalda admin emas. Avval botni kanalga admin qilib qo'shing, keyin qayta urinib ko'ring.")
            return
    except Exception as e:
        await message.answer(f"⚠️ Tekshirib bo'lmadi: {esc(str(e))}")
        return
    await db.add_sub_channel(chat.id, chat.title or str(chat.id), link)
    await message.answer(f"✅ Majburiy kanal qo'shildi: {esc(chat.title or '')}")


@router.message(Command("delchannel"))
async def delchannel(message: Message, command: CommandObject, bot: Bot):
    ref = (command.args or "").strip()
    if not ref:
        await message.answer("Foydalanish: /delchannel @kanal yoki -100...")
        return
    try:
        chat = await _resolve_chat(bot, ref)
        chat_id = chat.id
    except Exception:
        if not ref.lstrip("-").isdigit():
            await message.answer("Kanal topilmadi.")
            return
        chat_id = int(ref)
    ok = await db.remove_sub_channel(chat_id)
    await message.answer("🗑 O'chirildi." if ok else "Bunday kanal ro'yxatda yo'q.")


@router.message(Command("channels"))
async def channels(message: Message):
    rows = await db.list_sub_channels()
    post = await db.get_setting("post_channel")
    text = "📢 <b>Majburiy kanallar:</b>\n" + (
        "\n".join(f"• {esc(r['title'])} (<code>{r['chat_id']}</code>)" for r in rows) if rows else "yo'q"
    )
    text += f"\n\n📮 <b>Post kanali:</b> <code>{post}</code>" if post else "\n\n📮 Post kanali o'rnatilmagan"
    await message.answer(text)


# ---------- post kanali ----------
@router.message(Command("setpost"))
async def setpost(message: Message, command: CommandObject, bot: Bot):
    ref = (command.args or "").strip()
    if not ref:
        await message.answer("Foydalanish: /setpost @kanal yoki -100...")
        return
    try:
        chat = await _resolve_chat(bot, ref)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
    except Exception as e:
        await message.answer(f"⚠️ Kanal topilmadi: {esc(str(e))}")
        return
    if member.status not in ("administrator", "creator"):
        await message.answer("⚠️ Bot bu kanalda admin emas. Avval admin qilib qo'shing.")
        return
    await db.set_setting("post_channel", str(chat.id))
    await message.answer(f"✅ Post kanali o'rnatildi: {esc(chat.title or '')}")


@router.message(Command("unsetpost"))
async def unsetpost(message: Message):
    await db.delete_setting("post_channel")
    await message.answer("🗑 Post kanali o'chirildi.")


# ---------- statistika / xabar tarqatish ----------
@router.message(Command("stats"))
async def stats(message: Message):
    await message.answer(
        f"👥 Foydalanuvchilar: <b>{await db.count_users()}</b>\n🎬 Kinolar: <b>{await db.count_movies()}</b>"
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, bot: Bot):
    src = message.reply_to_message
    if not src:
        await message.answer("Tarqatmoqchi bo'lgan xabaringizga reply qilib /broadcast yozing.")
        return
    ids = await db.all_user_ids()
    await message.answer(f"📤 {len(ids)} ta foydalanuvchiga yuborilmoqda...")
    ok = fail = 0
    for uid in ids:
        try:
            await bot.copy_message(uid, src.chat.id, src.message_id)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Yuborildi: {ok}\n❌ Xato: {fail}")


# ---------- adminlar (faqat egasi) ----------
@router.message(Command("addadmin", "deladmin", "admins"))
async def manage_admins(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        await message.answer("Bu buyruq faqat bot egasi uchun.")
        return
    if command.command == "admins":
        ids = await db.list_admins()
        await message.answer("👮 Adminlar:\n" + ("\n".join(f"<code>{i}</code>" for i in ids) if ids else "yo'q"))
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(f"Foydalanish: /{command.command} ID")
        return
    if command.command == "addadmin":
        await db.add_admin(int(arg))
        await message.answer("✅ Admin qo'shildi.")
    else:
        ok = await db.remove_admin(int(arg))
        await message.answer("🗑 Admin o'chirildi." if ok else "Bunday admin yo'q.")
