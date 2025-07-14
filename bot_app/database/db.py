import asyncpg
from bot_app.utils import encryption

# Connection pool (initialized in startup)
_pool: asyncpg.Pool = None

async def init_db_pool(dsn: str):
    """Initialize the PostgreSQL connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(dsn)

# Utility: ensure pool is initialized
def _get_pool():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool

# ---------- User-related operations ----------

async def get_user_by_tg_id(telegram_id: int):
    """Fetch a user by Telegram ID. Returns a record or None."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT telegram_id, name_enc, plan, usage_count, usage_limit, language, notifications, password_hash, ydisk_token_enc FROM users WHERE telegram_id=$1", telegram_id)
        return row

async def create_user(telegram_id: int, name: str):
    """Create a new user with given telegram_id and name. Returns the new record."""
    pool = _get_pool()
    # Encrypt the name for storage
    name_enc = encryption.encrypt_str(name) if name else ""
    # Default plan and usage
    plan = "basic"
    usage_limit = 200  # basic plan monthly limit (for example)
    usage_count = 0
    language = "RU"
    notifications = True
    password_hash = ""  # no password set initially
    ydisk_token_enc = ""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, name_enc, plan, usage_count, usage_limit, language, notifications, password_hash, ydisk_token_enc)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (telegram_id) DO NOTHING
        """, telegram_id, name_enc, plan, usage_count, usage_limit, language, notifications, password_hash, ydisk_token_enc)
        # Return the user (fetch it)
        row = await conn.fetchrow("SELECT telegram_id, name_enc, plan, usage_count, usage_limit, language, notifications, password_hash, ydisk_token_enc FROM users WHERE telegram_id=$1", telegram_id)
        return row

async def update_user_name(user_id: int, new_name: str):
    pool = _get_pool()
    name_enc = encryption.encrypt_str(new_name)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET name_enc=$1 WHERE telegram_id=$2", name_enc, user_id)

async def update_user_password(user_id: int, new_password_hash: str):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash=$1 WHERE telegram_id=$2", new_password_hash, user_id)

async def update_user_language(user_id: int, new_lang: str):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language=$1 WHERE telegram_id=$2", new_lang, user_id)

async def update_user_notifications(user_id: int, enabled: bool):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET notifications=$1 WHERE telegram_id=$2", enabled, user_id)

async def update_user_ydisk_token(user_id: int, token: str):
    pool = _get_pool()
    token_enc = encryption.encrypt_str(token)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET ydisk_token_enc=$1 WHERE telegram_id=$2", token_enc, user_id)

# ---------- Student-related operations ----------

async def get_students_by_user(user_id: int):
    """Retrieve all students for a given user (decrypt fields for use)."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name_enc, subject_enc, level_enc, notes_enc FROM students WHERE user_id=$1 ORDER BY id", user_id)
        students = []
        for row in rows:
            name = encryption.decrypt_str(row["name_enc"]) if row["name_enc"] else ""
            subject = encryption.decrypt_str(row["subject_enc"]) if row["subject_enc"] else ""
            level = encryption.decrypt_str(row["level_enc"]) if row["level_enc"] else ""
            notes = encryption.decrypt_str(row["notes_enc"]) if row["notes_enc"] else ""
            students.append({
                "id": row["id"],
                "name": name,
                "subject": subject,
                "level": level,
                "notes": notes
            })
        return students

async def get_student(student_id: int):
    """Get a single student record (with decrypted fields)."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, user_id, name_enc, subject_enc, level_enc, notes_enc FROM students WHERE id=$1", student_id)
        if row:
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "name": encryption.decrypt_str(row["name_enc"]) if row["name_enc"] else "",
                "subject": encryption.decrypt_str(row["subject_enc"]) if row["subject_enc"] else "",
                "level": encryption.decrypt_str(row["level_enc"]) if row["level_enc"] else "",
                "notes": encryption.decrypt_str(row["notes_enc"]) if row["notes_enc"] else ""
            }
        return None

async def add_student(user_id: int, name: str, subject: str, level: str, notes: str):
    """Add a new student for the user (store encrypted values)."""
    pool = _get_pool()
    name_enc = encryption.encrypt_str(name)
    subject_enc = encryption.encrypt_str(subject)
    level_enc = encryption.encrypt_str(level)
    notes_enc = encryption.encrypt_str(notes) if notes else ""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO students (user_id, name_enc, subject_enc, level_enc, notes_enc)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
        """, user_id, name_enc, subject_enc, level_enc, notes_enc)
        return row["id"] if row else None

async def update_student(student_id: int, name: str, subject: str, level: str, notes: str):
    pool = _get_pool()
    name_enc = encryption.encrypt_str(name)
    subject_enc = encryption.encrypt_str(subject)
    level_enc = encryption.encrypt_str(level)
    notes_enc = encryption.encrypt_str(notes) if notes else ""
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE students SET name_enc=$1, subject_enc=$2, level_enc=$3, notes_enc=$4
            WHERE id=$5
        """, name_enc, subject_enc, level_enc, notes_enc, student_id)

async def delete_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM students WHERE id=$1", student_id)

# ---------- Subscription and usage ----------

async def increment_usage(user_id: int):
    """Increment usage count for user by 1."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_id=$1", user_id)

async def set_plan(user_id: int, plan: str, new_limit: int = None):
    """Update user's subscription plan (and optionally usage limit)."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        if new_limit is not None:
            await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_id=$3", plan, new_limit, user_id)
        else:
            await conn.execute("UPDATE users SET plan=$1 WHERE telegram_id=$2", plan, user_id)
