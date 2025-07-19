# /opt/RiverAI/worker/redis_cache.py

import redis.asyncio as redis
from worker import config

_client: redis.Redis | None = None

async def init_redis():
    """
    Initialize the Redis client using settings from config.
    Connects to host=config.REDIS_HOST, port=config.REDIS_PORT,
    and database index config.REDIS_DB_CACHE.
    """
    global _client
    _client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB_CACHE,  # ← используем REDIS_DB_CACHE из config
    )

def _get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis client is not initialized")
    return _client

async def get_conversation(user_id: int, student_id: int) -> str | None:
    """
    Retrieve chat history (JSON string) for given user & student from Redis.
    """
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    data = await client.get(key)
    return data.decode('utf-8') if data else None

async def save_conversation(user_id: int, student_id: int, conv_json: str) -> None:
    """
    Save chat history (JSON string) for given user & student to Redis.
    """
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.set(key, conv_json)

async def clear_conversation(user_id: int, student_id: int) -> None:
    """
    Delete chat history for given user & student from Redis.
    """
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.delete(key)
