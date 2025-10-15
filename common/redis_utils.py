# common/redis_utils.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)
_client: aioredis.Redis | None = None

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
        decode_responses=True,          # храним строки, JSON без b'...'
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
            _logger.error("🔴 Ошибка подключения к Redis %s:%s/%s: %s (attempt %d/%d)",
                          host, port, db, e, attempt, retries)
            await asyncio.sleep(min(delay, 10.0))
            delay *= 1.6

    # все попытки исчерпаны
    raise RuntimeError(f"Не удалось подключиться к Redis {host}:{port}/{db}: {last_err}")

def _get_client() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis client is not initialized. Call init_redis_pool(...) first.")
    return _client

def get_client() -> aioredis.Redis:
    return _get_client()

# ===== КОНТЕКСТ ЗАДАЧ =====

async def set_task_context(task_id: str, ctx: Dict[str, Any], ttl_sec: int = 3600) -> None:
    c = _get_client()
    await c.set(f"task_context:{task_id}", json.dumps(ctx, ensure_ascii=False), ex=ttl_sec)

async def get_context_by_task_id(task_id: str) -> Dict[str, Any]:
    c = _get_client()
    # совместимость c возможным старым ключом "context:"
    for key in (f"task_context:{task_id}", f"context:{task_id}"):
        raw = await c.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                _logger.exception("Ошибка парсинга JSON контекста (%s)", key)
                return {}
    return {}

# ===== ИСТОРИЯ ЧАТА =====

def _chat_key(user_id: int, student_id: int) -> str:
    return f"chat:{user_id}:{student_id}"

async def get_conversation(user_id: int, student_id: int) -> Optional[str]:
    c = _get_client()
    return await c.get(_chat_key(user_id, student_id))

async def save_conversation(user_id: int, student_id: int, history_json: str, ttl_sec: int = 7 * 24 * 3600) -> None:
    c = _get_client()
    await c.set(_chat_key(user_id, student_id), history_json, ex=ttl_sec)

async def clear_conversation(user_id: int, student_id: int) -> None:
    c = _get_client()
    await c.delete(_chat_key(user_id, student_id))
