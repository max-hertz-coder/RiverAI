import redis.asyncio as redis
from worker import config

_client: redis.Redis = None

async def init_redis():
    global _client
    _client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)

def _get_client():
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client

async def get_conversation(user_id: int, student_id: int):
    """Retrieve chat history from Redis for given user & student."""
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    data = await client.get(key)
    if data:
        # store as plaintext JSON string
        return data.decode('utf-8')
    return None

async def save_conversation(user_id: int, student_id: int, conv_json: str):
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.set(key, conv_json)

async def clear_conversation(user_id: int, student_id: int):
    client = _get_client()
    key = f"chat:{user_id}:{student_id}"
    await client.delete(key)
