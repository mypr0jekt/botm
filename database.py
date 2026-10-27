import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    part_no INTEGER NOT NULL,
    file_id TEXT NOT NULL,
    file_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sub_channels (
    chat_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


async def _connect():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db():
    db = await _connect()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


async def _exec(query: str, params: tuple = ()):
    db = await _connect()
    try:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid, cur.rowcount
    finally:
        await db.close()


async def _fetchall(query: str, params: tuple = ()):
    db = await _connect()
    try:
        cur = await db.execute(query, params)
        return await cur.fetchall()
    finally:
        await db.close()


async def _fetchone(query: str, params: tuple = ()):
    db = await _connect()
    try:
        cur = await db.execute(query, params)
        return await cur.fetchone()
    finally:
        await db.close()


# ---------- users ----------
async def add_user(user_id: int):
    await _exec("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))


async def count_users() -> int:
    row = await _fetchone("SELECT COUNT(*) AS c FROM users")
    return row["c"]


async def all_user_ids() -> list[int]:
    rows = await _fetchall("SELECT user_id FROM users")
    return [r["user_id"] for r in rows]


# ---------- admins ----------
async def add_admin(user_id: int):
    await _exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))


async def remove_admin(user_id: int) -> bool:
    _, n = await _exec("DELETE FROM admins WHERE user_id = ?", (user_id,))
    return n > 0


async def is_admin_db(user_id: int) -> bool:
    row = await _fetchone("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return row is not None


async def list_admins() -> list[int]:
    rows = await _fetchall("SELECT user_id FROM admins")
    return [r["user_id"] for r in rows]


# ---------- movies ----------
async def next_code() -> str:
    rows = await _fetchall("SELECT code FROM movies")
    nums = [int(r["code"]) for r in rows if r["code"].isdigit()]
    return str(max(nums) + 1 if nums else 1)


async def code_exists(code: str) -> bool:
    row = await _fetchone("SELECT 1 FROM movies WHERE code = ?", (code,))
    return row is not None


async def add_movie(code: str, title: str, language: str, parts: list[tuple[str, str]]) -> int:
    db = await _connect()
    try:
        cur = await db.execute(
            "INSERT INTO movies (code, title, language) VALUES (?, ?, ?)",
            (code, title, language),
        )
        movie_id = cur.lastrowid
        for i, (file_id, file_type) in enumerate(parts, start=1):
            await db.execute(
                "INSERT INTO parts (movie_id, part_no, file_id, file_type) VALUES (?, ?, ?, ?)",
                (movie_id, i, file_id, file_type),
            )
        await db.commit()
        return movie_id
    finally:
        await db.close()


async def get_movie(code: str):
    return await _fetchone("SELECT * FROM movies WHERE code = ?", (code,))


async def get_parts(movie_id: int):
    return await _fetchall(
        "SELECT * FROM parts WHERE movie_id = ? ORDER BY part_no", (movie_id,)
    )


async def delete_movie(code: str) -> bool:
    _, n = await _exec("DELETE FROM movies WHERE code = ?", (code,))
    return n > 0


async def list_movies(limit: int = 50):
    return await _fetchall(
        """SELECT m.code, m.title, m.language,
                  (SELECT COUNT(*) FROM parts p WHERE p.movie_id = m.id) AS parts
           FROM movies m ORDER BY m.id DESC LIMIT ?""",
        (limit,),
    )


async def count_movies() -> int:
    row = await _fetchone("SELECT COUNT(*) AS c FROM movies")
    return row["c"]


# ---------- subscription channels ----------
async def add_sub_channel(chat_id: int, title: str, link: str):
    await _exec(
        "INSERT OR REPLACE INTO sub_channels (chat_id, title, link) VALUES (?, ?, ?)",
        (chat_id, title, link),
    )


async def remove_sub_channel(chat_id: int) -> bool:
    _, n = await _exec("DELETE FROM sub_channels WHERE chat_id = ?", (chat_id,))
    return n > 0


async def list_sub_channels():
    return await _fetchall("SELECT * FROM sub_channels")


# ---------- settings ----------
async def set_setting(key: str, value: str):
    await _exec("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


async def get_setting(key: str):
    row = await _fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else None


async def delete_setting(key: str):
    await _exec("DELETE FROM settings WHERE key = ?", (key,))
