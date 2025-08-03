import asyncpg
from bot_app.utils import encryption
from datetime import datetime, timedelta

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
    async with pool.acquire() as conn:
        # Используем зашифрованные колонки
        row = await conn.fetchrow("""
            SELECT telegram_id, name_enc, plan, usage_count, usage_limit,
                   language, notifications, password_hash,
                   ydisk_token_enc
            FROM users WHERE telegram_id=$1
        """, telegram_id)
        if row:
            return {
                "telegram_id": row["telegram_id"],
                "name": encryption.decrypt_str(row["name_enc"]) if row["name_enc"] else "",
                "plan": row["plan"],
                "usage_count": row["usage_count"],
                "usage_limit": row["usage_limit"],
                "language": row["language"],
                "notifications": row["notifications"],
                "password_hash": row["password_hash"],
                "ydisk_token_enc": row["ydisk_token_enc"],
                "hide_disk_prompt": False,
                "tokens_prompt_total": 0,
                "tokens_gen_total": 0,
                "subscription_expires": None,
                "trial_used": False,
                "students_limit": 3
            }
        return None

async def create_user(telegram_id: int, name: str):
    pool = _get_pool()
    
    # Используем зашифрованные колонки
    async with pool.acquire() as conn:
        name_enc = encryption.encrypt_str(name) if name else ""
        plan = "basic"
        usage_limit = 200
        usage_count = 0
        language = "RU"
        notifications = True
        password_hash = ""
        ydisk_token_enc = ""
        
        await conn.execute("""
            INSERT INTO users (
                telegram_id, name_enc, plan, usage_count, usage_limit,
                language, notifications, password_hash, ydisk_token_enc
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (telegram_id) DO NOTHING
        """, telegram_id, name_enc, plan, usage_count, usage_limit,
             language, notifications, password_hash, ydisk_token_enc)
        
        return await get_user_by_tg_id(telegram_id)

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

async def set_user_disk_prompt_disabled(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET hide_disk_prompt=true WHERE telegram_id=$1", user_id)

# ---------- Student-related operations ----------

async def get_students_by_user(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        # Используем обычные колонки для students
        rows = await conn.fetch("""
            SELECT id, name, subject, level, notes, usage_count, tokens_prompt_total, tokens_gen_total
            FROM students WHERE user_id=$1 ORDER BY id
        """, user_id)
        students = []
        for row in rows:
            students.append({
                "id": row["id"],
                "name": row["name"],
                "subject": row["subject"],
                "level": row["level"],
                "notes": row["notes"] if row["notes"] else "",
                "usage_count": row["usage_count"],
                "tokens_prompt_total": row["tokens_prompt_total"],
                "tokens_gen_total": row["tokens_gen_total"]
            })
        return students

async def get_student_by_id(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, user_id, name, subject, level, notes, usage_count, tokens_prompt_total, tokens_gen_total
            FROM students WHERE id=$1
        """, student_id)
        if row:
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "name": row["name"],
                "subject": row["subject"],
                "level": row["level"],
                "notes": row["notes"] if row["notes"] else "",
                "usage_count": row["usage_count"],
                "tokens_prompt_total": row["tokens_prompt_total"],
                "tokens_gen_total": row["tokens_gen_total"]
            }
        return None

async def create_student(user_id: int, name: str, subject: str, level: str, notes: str):
    pool = _get_pool()
    async with pool.acquire() as conn:
        # Используем обычные колонки для students
        row = await conn.fetchrow("""
            INSERT INTO students (
                user_id, name, subject, level, notes
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
        user_id, name, subject, level, notes if notes else "")
        
        return row["id"] if row else None

async def update_student_name(student_id: int, new_name: str):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE students SET name=$1 WHERE id=$2", new_name, student_id)

async def delete_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM students WHERE id=$1", student_id)

# ---------- Usage & Stats Tracking ----------

async def increment_usage(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_id=$1", user_id)

async def increment_token_usage(user_id: int, prompt_tokens: int, gen_tokens: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total = tokens_gen_total + $2
            WHERE telegram_id=$3
        """, prompt_tokens, gen_tokens, user_id)

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
    async with pool.acquire() as conn:
        if new_limit is not None:
            await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_id=$3", plan, new_limit, user_id)
        else:
            # по умолчанию ставим лимит в зависимости от плана
            default_limit = 1000 if plan == "premium" else 200
            await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_id=$3", plan, default_limit, user_id)

async def update_user_plan(user_id: int, plan: str, students: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET plan=$1, students_limit=$2, subscription_expires=$3
            WHERE telegram_id=$4
        """, plan, students, datetime.now() + timedelta(days=30), user_id)

async def delete_user(user_id: int):
    """Удаляет пользователя и всех его учеников (через ON DELETE CASCADE)."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE telegram_id=$1", user_id)

# ---------- Subscription operations ----------

async def has_active_subscription(user_id: int) -> bool:
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT subscription_expires FROM users WHERE telegram_id=$1", user_id)
        if row:
            return datetime.fromisoformat(str(row)) > datetime.now()
        return False

async def mark_trial_used(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_used=true WHERE telegram_id=$1", user_id)