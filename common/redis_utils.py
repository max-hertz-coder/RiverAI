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
    try:
        _client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            encoding="utf-8"
        )
        # Проверяем подключение
        await _client.ping()
        print(f"✅ Redis подключен: {host}:{port}/{db}")
    except Exception as e:
        print(f"🔴 Ошибка подключения к Redis {host}:{port}/{db}: {e}")
        raise

# ========= Задания =========

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

# ========= Контексты задач =========

async def save_context(task_id: str, context: dict):
    """Сохраняет контекст задачи в Redis"""
    key = f"task_context:{task_id}"
    try:
        await _get_client().set(key, json.dumps(context), ex=3600)
        print(f"🔧 Контекст сохранен: {key}")
    except Exception as e:
        print(f"🔴 Ошибка сохранения контекста {key}: {e}")
        raise

async def get_context_by_task_id(task_id: str) -> dict | None:
    """Получает контекст задачи по task_id"""
    key = f"task_context:{task_id}"
    try:
        data = await _get_client().get(key)
        if data:
            print(f"🔧 Контекст найден: {key}")
            return json.loads(data)
        else:
            print(f"🔴 Контекст не найден: {key}")
            return None
    except Exception as e:
        print(f"🔴 Ошибка получения контекста {key}: {e}")
        return None

async def delete_context_by_task_id(task_id: str) -> None:
    """Удаляет контекст задачи"""
    key = f"task_context:{task_id}"
    await _get_client().delete(key)

async def cleanup_task_context(task_id: str) -> None:
    """Очищает контекст задачи после обработки"""
    await delete_context_by_task_id(task_id)

# ========= Диалоги =========

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

# ========= Solutions PDF =========

async def save_last_solutions_file(user_id: int, file_b64: str) -> None:
    """Сохраняет Solutions.pdf в base64 на 1 час"""
    key = f"solutions:{user_id}"
    await _get_client().set(key, file_b64, ex=3600)

async def get_last_solutions_file(user_id: int) -> str | None:
    """Получает последний сохранённый Solutions.pdf (base64)"""
    key = f"solutions:{user_id}"
    return await _get_client().get(key)
