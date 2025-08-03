import asyncpg
from bot_app.utils import encryption
from bot_app.utils.identity import hash_telegram_id
from datetime import datetime, timedelta  # ← добавь timedelta

_pool: asyncpg.Pool = None

async def init_db_pool(dsn: str):
    global _pool
    _pool = await asyncpg.create_pool(dsn)

def _get_pool():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool

# ---------- User-related operations ----------

async def get_user_by_tg_id(telegram_id: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(telegram_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT telegram_hash, name_enc, plan, usage_count, usage_limit,
                   tokens_prompt_total, tokens_gen_total,
                   language, notifications, password_hash,
                   ydisk_token_enc, hide_disk_prompt,
                   subscription_expires, trial_used
            FROM users WHERE telegram_hash=$1
        """, tg_hash)
        return row


async def create_user(telegram_id: int, name: str):
    pool = _get_pool()
    name_enc = encryption.encrypt_str(name) if name else ""
    plan = "basic"
    usage_limit = 200
    usage_count = 0
    language = "RU"
    notifications = True
    password_hash = ""
    ydisk_token_enc = ""
    tokens_prompt_total = 0
    tokens_gen_total = 0
    hide_disk_prompt = False
    tg_hash = hash_telegram_id(telegram_id)
    now = datetime.now()
    trial_end = now + timedelta(days=14)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (
                telegram_hash, name_enc, plan, usage_count, usage_limit,
                tokens_prompt_total, tokens_gen_total,
                language, notifications, password_hash,
                ydisk_token_enc, hide_disk_prompt, subscription_expires, trial_used
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            ON CONFLICT (telegram_hash) DO NOTHING
        """, tg_hash, name_enc, plan, usage_count, usage_limit,
             tokens_prompt_total, tokens_gen_total,
             language, notifications, password_hash,
             ydisk_token_enc, hide_disk_prompt, trial_end, False)
        return await get_user_by_tg_id(telegram_id)


async def update_user_name(user_id: int, new_name: str):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    name_enc = encryption.encrypt_str(new_name)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET name_enc=$1 WHERE telegram_hash=$2", name_enc, tg_hash)

async def update_user_password(user_id: int, new_password_hash: str):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash=$1 WHERE telegram_hash=$2", new_password_hash, tg_hash)

async def update_user_language(user_id: int, new_lang: str):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language=$1 WHERE telegram_hash=$2", new_lang, tg_hash)

async def update_user_notifications(user_id: int, enabled: bool):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET notifications=$1 WHERE telegram_hash=$2", enabled, tg_hash)

async def update_user_ydisk_token(user_id: int, token: str):
    pool = _get_pool()
    token_enc = encryption.encrypt_ydisk_token(token)
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET ydisk_token_enc=$1 WHERE telegram_hash=$2", token_enc, tg_hash)

async def set_user_disk_prompt_disabled(user_id: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET hide_disk_prompt=true WHERE telegram_hash=$1", tg_hash)

# ---------- Student-related operations ----------



async def get_students_by_user(user_id: int):
    pool = _get_pool()
    user_hash = hash_telegram_id(user_id)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name_enc, subject_enc, level_enc, notes_enc
            FROM students
            WHERE user_hash = $1
            ORDER BY id
        """, user_hash)

        students = []
        for row in rows:
            students.append({
                "id": row["id"],
                "name": encryption.decrypt_str(row["name_enc"]),
                "subject": encryption.decrypt_str(row["subject_enc"]),
                "level": encryption.decrypt_str(row["level_enc"]),
                "notes": encryption.decrypt_str(row["notes_enc"]) if row["notes_enc"] else ""
            })

        return students


async def get_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, user_id, name_enc, subject_enc, level_enc, notes_enc
            FROM students WHERE id=$1
        """, student_id)
        if row:
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "name": encryption.decrypt_str(row["name_enc"]),
                "subject": encryption.decrypt_str(row["subject_enc"]),
                "level": encryption.decrypt_str(row["level_enc"]),
                "notes": encryption.decrypt_str(row["notes_enc"]) if row["notes_enc"] else ""
            }
        return None

async def add_student(user_id: int, name: str, subject: str, level: str, notes: str):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO students (
                user_id, name_enc, subject_enc, level_enc, notes_enc
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
        tg_hash,
        encryption.encrypt_str(name),
        encryption.encrypt_str(subject),
        encryption.encrypt_str(level),
        encryption.encrypt_str(notes) if notes else "")
        return row["id"] if row else None
    

async def update_student(student_id: int, name: str, subject: str, level: str, notes: str):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE students
            SET name_enc=$1, subject_enc=$2, level_enc=$3, notes_enc=$4
            WHERE id=$5
        """,
        encryption.encrypt_str(name),
        encryption.encrypt_str(subject),
        encryption.encrypt_str(level),
        encryption.encrypt_str(notes) if notes else "",
        student_id)


async def delete_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM students WHERE id=$1", student_id)

# ---------- Usage & Stats Tracking ----------

async def increment_usage(user_id: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_hash=$1", tg_hash)

async def increment_token_usage(user_id: int, prompt_tokens: int, gen_tokens: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total = tokens_gen_total + $2
            WHERE telegram_hash=$3
        """, prompt_tokens, gen_tokens, tg_hash)

async def increment_student_token_usage(student_id: int, prompt_tokens: int, gen_tokens: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE students SET
                usage_count = usage_count + 1,
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total = tokens_gen_total + $2
            WHERE id=$3
        """, prompt_tokens, gen_tokens, student_id)


async def set_plan(user_id: int, plan: str, new_limit: int = None):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        if new_limit is not None:
            await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_hash=$3", plan, new_limit, tg_hash)
        else:
            default_limit = 1000 if plan == "premium" else 200
            await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_hash=$3", plan, default_limit, tg_hash)

async def delete_user(user_id: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE telegram_hash=$1", tg_hash)

# ---------- Подписка ----------



async def set_subscription(user_id: int, plan: str, students: int, until_date):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET plan=$1, students_limit=$2, subscription_expires=$3
            WHERE telegram_hash=$4
        """, plan, students, until_date, tg_hash)

async def has_active_subscription(user_id: int) -> bool:
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT subscription_expires FROM users WHERE telegram_hash=$1", tg_hash)
        if row:
            return datetime.fromisoformat(str(row)) > datetime.now()
        return False

async def mark_trial_used(user_id: int):
    pool = _get_pool()
    tg_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_used=true WHERE telegram_hash=$1", tg_hash)
