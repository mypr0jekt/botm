# Kino bot

aiogram 3.x + SQLite Telegram kino/serial boti.

## Imkoniyatlar
- Majburiy obuna (kanallar bot ichidan boshqariladi)
- Kino kodi bo'yicha qidirish
- Ko'p qismli seriallar
- Kanalga post + «🎬 Tomosha qilish» tugmasi
- Admin panel: kino qo'shish/o'chirish, statistika, xabar tarqatish

## Ishga tushirish
```bash
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN va OWNER_ID ni yozing
python main.py
```

## Sozlash (botda)
1. Botni kerakli kanallarga **admin** qilib qo'shing (Telegram qoidasi: bot o'zini admin qila olmaydi).
2. `/addchannel @kanal` — majburiy obuna kanali
3. `/setpost @kanal` — kinolar tashlanadigan kanal
4. `/addmovie` — nom → til → kod → video(lar) → `/done`

Barcha buyruqlar: `/admin`
