import asyncio
import time

import aiosqlite

from config import DB_PATH, OWNER_ID

_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()
_admins: set[int] = set()
_seen_users: set[int] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    full_name TEXT,
    username  TEXT,
    joined_at INTEGER,
    active    INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS channels (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE,
    title   TEXT,
    link    TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS movies (
    code        INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    language    TEXT NOT NULL,
    poster_id   TEXT,
    poster_type TEXT,
    views       INTEGER DEFAULT 0,
    created_at  INTEGER
);
CREATE TABLE IF NOT EXISTS parts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_code INTEGER NOT NULL,
    part_no    INTEGER NOT NULL,
    file_id    TEXT NOT NULL,
    file_type  TEXT NOT NULL,
    UNIQUE (movie_code, part_no)
);
CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
"""


async def init() -> None:
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.executescript(SCHEMA)
    await _db.commit()
    cur = await _db.execute("SELECT user_id FROM admins")
    _admins.update(r["user_id"] for r in await cur.fetchall())


async def close() -> None:
    if _db:
        await _db.close()


# ---------- Adminlar ----------

def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in _admins


async def add_admin(user_id: int) -> None:
    await _db.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (user_id,))
    await _db.commit()
    _admins.add(user_id)


async def del_admin(user_id: int) -> None:
    await _db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    await _db.commit()
    _admins.discard(user_id)


def list_admins() -> list[int]:
    return sorted(_admins)


# ---------- Foydalanuvchilar ----------

async def add_user(user_id: int, full_name: str, username: str | None) -> None:
    if user_id in _seen_users:
        return
    await _db.execute(
        "INSERT INTO users(user_id, full_name, username, joined_at, active) "
        "VALUES (?,?,?,?,1) "
        "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, "
        "username=excluded.username, active=1",
        (user_id, full_name, username, int(time.time())),
    )
    await _db.commit()
    _seen_users.add(user_id)
    if len(_seen_users) > 200_000:
        _seen_users.clear()


async def set_inactive(user_id: int) -> None:
    await _db.execute("UPDATE users SET active=0 WHERE user_id=?", (user_id,))
    await _db.commit()
    _seen_users.discard(user_id)


async def active_user_ids() -> list[int]:
    cur = await _db.execute("SELECT user_id FROM users WHERE active=1")
    return [r["user_id"] for r in await cur.fetchall()]


async def stats() -> dict:
    day_ago = int(time.time()) - 86400
    q = {
        "users": "SELECT COUNT(*) FROM users",
        "active": "SELECT COUNT(*) FROM users WHERE active=1",
        "new_24h": f"SELECT COUNT(*) FROM users WHERE joined_at >= {day_ago}",
        "movies": "SELECT COUNT(*) FROM movies",
        "parts": "SELECT COUNT(*) FROM parts",
        "views": "SELECT COALESCE(SUM(views),0) FROM movies",
    }
    out = {}
    for k, sql in q.items():
        cur = await _db.execute(sql)
        out[k] = (await cur.fetchone())[0]
    return out


# ---------- Sozlamalar ----------

async def get_setting(key: str) -> str | None:
    cur = await _db.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else None


async def set_setting(key: str, value: str | None) -> None:
    if value is None:
        await _db.execute("DELETE FROM settings WHERE key=?", (key,))
    else:
        await _db.execute(
            "INSERT INTO settings(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    await _db.commit()


# ---------- Majburiy obuna kanallari ----------

async def list_channels() -> list[aiosqlite.Row]:
    cur = await _db.execute("SELECT * FROM channels ORDER BY id")
    return await cur.fetchall()


async def add_channel(chat_id: int, title: str, link: str) -> None:
    await _db.execute(
        "INSERT INTO channels(chat_id, title, link) VALUES (?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, link=excluded.link",
        (chat_id, title, link),
    )
    await _db.commit()


async def del_channel(channel_id: int) -> None:
    await _db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    await _db.commit()


# ---------- Kinolar ----------

async def add_movie(
    title: str,
    language: str,
    poster_id: str,
    poster_type: str,
    parts: list[tuple[str, str]],
) -> int:
    """Kinoni qismlari bilan saqlaydi va yangi kodni qaytaradi."""
    async with _lock:
        cur = await _db.execute("SELECT COALESCE(MAX(code), 99) + 1 FROM movies")
        code = (await cur.fetchone())[0]
        await _db.execute(
            "INSERT INTO movies(code, title, language, poster_id, poster_type, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (code, title, language, poster_id, poster_type, int(time.time())),
        )
        await _db.executemany(
            "INSERT INTO parts(movie_code, part_no, file_id, file_type) VALUES (?,?,?,?)",
            [(code, i, fid, ft) for i, (fid, ft) in enumerate(parts, 1)],
        )
        await _db.commit()
    return code


async def get_movie(code: int):
    cur = await _db.execute("SELECT * FROM movies WHERE code=?", (code,))
    return await cur.fetchone()


async def get_part(code: int, part_no: int):
    cur = await _db.execute(
        "SELECT * FROM parts WHERE movie_code=? AND part_no=?", (code, part_no)
    )
    return await cur.fetchone()


async def count_parts(code: int) -> int:
    cur = await _db.execute("SELECT COUNT(*) FROM parts WHERE movie_code=?", (code,))
    return (await cur.fetchone())[0]


async def inc_views(code: int) -> None:
    await _db.execute("UPDATE movies SET views = views + 1 WHERE code=?", (code,))
    await _db.commit()


async def delete_movie(code: int) -> None:
    await _db.execute("DELETE FROM parts WHERE movie_code=?", (code,))
    await _db.execute("DELETE FROM movies WHERE code=?", (code,))
    await _db.commit()


async def count_movies() -> int:
    cur = await _db.execute("SELECT COUNT(*) FROM movies")
    return (await cur.fetchone())[0]


async def list_movies(offset: int, limit: int):
    cur = await _db.execute(
        "SELECT * FROM movies ORDER BY code DESC LIMIT ? OFFSET ?", (limit, offset)
    )
    return await cur.fetchall()


async def search_movies(query: str, limit: int = 10):
    like = f"%{query.strip()}%"
    cur = await _db.execute(
        "SELECT * FROM movies WHERE title LIKE ? ORDER BY views DESC, code DESC LIMIT ?",
        (like, limit),
    )
    return await cur.fetchall()
