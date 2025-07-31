# bot_app/redis_cache.py
import redis.asyncio as redis
from bot_app import config

_client: redis.Redis | None = None

def _get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client

async def init_redis_pool(host: str, port: int, db: int) -> None:
    """
    Инициализирует Redis-клиент для хранения промежуточных данных (raw_tasks).
    """
    global _client
    _client = redis.Redis(
        host=host,
        port=port,
        db=db,
        decode_responses=True,
        encoding="utf-8"
    )

async def save_raw_tasks(user_id: int, student_id: int, raw: str) -> None:
    """
    Сохраняет raw-текст сгенерированных заданий в Redis (истекает через час).
    """
    key = f"raw_tasks:{user_id}:{student_id}"
    await _get_client().set(key, raw, ex=3600)

async def get_raw_tasks(user_id: int, student_id: int) -> str | None:
    """
    Возвращает сохранённый raw-текст заданий из Redis.
    """
    key = f"raw_tasks:{user_id}:{student_id}"
    return await _get_client().get(key)


import json

async def save_context(task_id: str, context: dict):
    key = f"task_context:{task_id}"
    await _get_client().set(key, json.dumps(context), ex=3600)

async def get_context_by_task_id(task_id: str) -> dict | None:
    key = f"task_context:{task_id}"
    data = await _get_client().get(key)
    return json.loads(data) if data else None

async def delete_context_by_task_id(task_id: str) -> None:
    key = f"task_context:{task_id}"
    await _get_client().delete(key)