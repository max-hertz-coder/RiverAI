import redis.asyncio as redis
from worker import config

_client: redis.Redis = None

async def init_redis_pool(host: str, port: int, db: int = 0) -> None:
    """
    Унифицированный инициализатор Redis-клиента (используется в main.py).
    """
    global _client
    _client = redis.Redis(
        host=host,
        port=port,
        db=db,
        decode_responses=True,
        encoding="utf-8"
    )

def _get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client

async def get_conversation(user_id: int, student_id: int) -> str | None:
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    data = await client.get(key)
    return data if data else None

async def save_conversation(user_id: int, student_id: int, conv_json: str) -> None:
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.set(key, conv_json)

async def clear_conversation(user_id: int, student_id: int) -> None:
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.delete(key)

# bot_app/redis_cache.py (поместите рядом с get_conversation и т.п.)

async def save_raw_tasks(user_id: int, student_id: int, raw: str) -> None:
    """
    Сохраняет raw-текст сгенерированных заданий в Redis по ключу:
      raw_tasks:{user_id}:{student_id}
    """
    client = _get_client()
    key = f"raw_tasks:{user_id}:{student_id}"
    # Сохраняем на 1 час
    await client.set(key, raw, ex=3600)

async def get_raw_tasks(user_id: int, student_id: int) -> str | None:
    """
    Забирает raw-текст заданий из Redis.
    """
    client = _get_client()
    key = f"raw_tasks:{user_id}:{student_id}"
    return await client.get(key)
