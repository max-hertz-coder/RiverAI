# common/redis_utils.py
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)
_client: aioredis.Redis | None = None

__all__ = [
    "init_redis_pool",
    "get_client",
    "set_task_context",
    "get_context_by_task_id",
    "cleanup_task_context",
    # совместимость со старыми импортами
    "save_context",
    "get_task_context",
    "clear_conversation",
    "save_conversation",
    "get_conversation",
]

# ======================== базовые утилиты ========================

def _int(v: Any, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d

async def init_redis_pool(
    host: str,
    port: int | str,
    db: int | str,
    *,
    retries: int = 20,
    base_delay: float = 0.5,
) -> None:
    """
    Инициализирует соединение с Redis с экспоненциальными ретраями.
    Не падаем сразу при старте, если Redis ещё не поднялся или перезапускается.
    """
    global _client
    port = _int(port, 6379)
    db = _int(db, 1)

    _client = aioredis.Redis(
        host=host,
        port=port,
        db=db,
        decode_responses=True,          # строки/JSON без b'...'
        socket_keepalive=True,
        socket_timeout=5,
        socket_connect_timeout=3,
        health_check_interval=30,
    )

    delay = base_delay
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            await _client.ping()
            _logger.info("✅ Redis подключен: %s:%s/%s", host, port, db)
            return
        except Exception as e:
            last_err = e
            _logger.error(
                "🔴 Ошибка подключения к Redis %s:%s/%s: %s (attempt %d/%d)",
                host, port, db, e, attempt, retries
            )
            await asyncio.sleep(min(delay, 10.0))
            delay *= 1.6

    raise RuntimeError(f"Не удалось подключиться к Redis {host}:{port}/{db}: {last_err}")

def _get_client() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis client is not initialized. Call init_redis_pool(...) first.")
    return _client

def get_client() -> aioredis.Redis:
    return _get_client()

# ======================== контекст задач ========================

_TASK_CTX_KEYS = (
    "task_context:{task_id}",  # новый ключ
    "context:{task_id}",       # старый ключ (совместимость)
    "task:ctx:{task_id}",      # на всякий случай (если где-то оставался)
)

def _ctx_keys_for(task_id: str) -> list[str]:
    return [k.format(task_id=task_id) for k in _TASK_CTX_KEYS]

async def set_task_context(task_id: str, ctx: Dict[str, Any], ttl_sec: int = 3600) -> None:
    """
    Сохранить контекст задачи (новый API).
    """
    c = _get_client()
    key = _ctx_keys_for(task_id)[0]  # используем новый ключ
    await c.set(key, json.dumps(ctx, ensure_ascii=False), ex=ttl_sec)

# --- совместимость: старое имя функции ---
async def save_context(task_id: str, ctx: Dict[str, Any], ttl_sec: int = 3600) -> None:
    """
    Совместимость со старым кодом: alias для set_task_context(...).
    """
    await set_task_context(task_id, ctx, ttl_sec=ttl_sec)

async def get_context_by_task_id(task_id: str) -> Dict[str, Any]:
    """
    Получить контекст по task_id. Поддерживает старые ключи.
    """
    c = _get_client()
    for key in _ctx_keys_for(task_id):
        raw = await c.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                _logger.exception("Ошибка парсинга JSON контекста (%s)", key)
                return {}
    return {}

# --- совместимость: старое имя функции ---
async def get_task_context(task_id: str) -> Dict[str, Any]:
    """
    Совместимость со старым кодом: alias для get_context_by_task_id(...).
    """
    return await get_context_by_task_id(task_id)

async def cleanup_task_context(task_id: str) -> None:
    """
    Удалить контекст по всем возможным ключам (чистка).
    """
    c = _get_client()
    keys = _ctx_keys_for(task_id)
    if keys:
        await c.delete(*keys)

# ======================== история чата ========================

def _chat_key(user_id: int, student_id: int) -> str:
    return f"chat:{user_id}:{student_id}"

async def get_conversation(user_id: int, student_id: int) -> Optional[str]:
    c = _get_client()
    return await c.get(_chat_key(user_id, student_id))

async def save_conversation(
    user_id: int,
    student_id: int,
    history_json: str,
    ttl_sec: int = 7 * 24 * 3600
) -> None:
    c = _get_client()
    await c.set(_chat_key(user_id, student_id), history_json, ex=ttl_sec)

async def clear_conversation(user_id: int, student_id: int) -> None:
    c = _get_client()
    await c.delete(_chat_key(user_id, student_id))
