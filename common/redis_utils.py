import redis.asyncio as redis
import json
import os

_client: redis.Redis | None = None

def _get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client

async def init_redis_pool(host: str, port: int, db: int) -> None:
    """
    Инициализирует Redis-клиент для хранения промежуточных данных.
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

async def save_context(task_id: str, context: dict):
    """Сохраняет контекст задачи в Redis"""
    key = f"task_context:{task_id}"
    await _get_client().set(key, json.dumps(context), ex=3600)

async def get_context_by_task_id(task_id: str) -> dict | None:
    """Получает контекст задачи по task_id"""
    key = f"task_context:{task_id}"
    data = await _get_client().get(key)
    return json.loads(data) if data else None

async def delete_context_by_task_id(task_id: str) -> None:
    """Удаляет контекст задачи"""
    key = f"task_context:{task_id}"
    await _get_client().delete(key)

async def cleanup_task_context(task_id: str) -> None:
    """Очищает контекст задачи после обработки"""
    await delete_context_by_task_id(task_id)

# Функции для работы с диалогами
async def save_conversation(user_id: int, student_id: int, history_json: str) -> None:
    """Сохраняет историю диалога в Redis"""
    key = f"conversation:{user_id}:{student_id}"
    await _get_client().set(key, history_json, ex=3600)

async def get_conversation(user_id: int, student_id: int) -> str | None:
    """Получает историю диалога из Redis"""
    key = f"conversation:{user_id}:{student_id}"
    return await _get_client().get(key)

async def clear_conversation(user_id: int, student_id: int) -> None:
    """Очищает историю диалога"""
    key = f"conversation:{user_id}:{student_id}"
    await _get_client().delete(key) 