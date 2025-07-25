import redis.asyncio as redis
from worker import config

_client: redis.Redis = None

async def init_redis() -> None:
    """
    Инициализируем клиент Redis для кэша (используем DB из config.REDIS_DB).
    """
    global _client
    # config.REDIS_DB — та переменная, которая у вас определена в worker/config.py
    _client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB
    )

def _get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client

async def get_conversation(user_id: int, student_id: int) -> str | None:
    """
    Получить историю чата из Redis (JSON-строка).
    """
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    data = await client.get(key)
    return data.decode("utf-8") if data else None

async def save_conversation(user_id: int, student_id: int, conv_json: str) -> None:
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.set(key, conv_json)

async def clear_conversation(user_id: int, student_id: int) -> None:
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.delete(key)
