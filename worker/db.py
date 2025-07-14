import asyncpg
from worker import config
from worker.utils import encryption

_pool: asyncpg.Pool = None

async def init_db_pool():
    global _pool
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    _pool = await asyncpg.create_pool(dsn)

def _get_pool():
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool

async def get_user(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT telegram_id, plan, ydisk_token_enc FROM users WHERE telegram_id=$1", user_id)

async def get_student(student_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, user_id, name_enc, subject_enc, level_enc, notes_enc FROM students WHERE id=$1", student_id)
        return row

async def increment_usage(user_id: int):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_id=$1", user_id)
