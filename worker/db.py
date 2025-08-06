# /opt/RiverAI/worker/db.py

import asyncpg
from worker import config
from worker.utils import encryption  # или откуда у вас берётся encryption

_pool: asyncpg.Pool = None

async def init_db_pool(dsn: str | None = None):
    """
    Initialize the PostgreSQL connection pool.
    Если DSN не передан, берём его из config.
    """
    global _pool
    if dsn is None:
        dsn = (
            f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        )
    _pool = await asyncpg.create_pool(dsn)

def _get_pool():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool


async def get_user(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT telegram_id, plan, ydisk_token_enc FROM users WHERE telegram_id=$1", user_id)

async def get_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, user_id, name, subject, level, notes FROM students WHERE id=$1", student_id)
        return row

async def increment_usage(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_id=$1", user_id)

async def increment_token_usage(user_id: int, prompt_tokens: int, gen_tokens: int):
    """
    Увеличивает счетчики токенов для пользователя
    """
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total = tokens_gen_total + $2
            WHERE telegram_id=$3
        """, prompt_tokens, gen_tokens, user_id)

async def increment_student_token_usage(student_id: int, prompt_tokens: int, gen_tokens: int):
    """
    Увеличивает счетчики токенов для ученика
    """
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE students SET
                usage_count = usage_count + 1,
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total = tokens_gen_total + $2
            WHERE id=$3
        """, prompt_tokens, gen_tokens, student_id)
