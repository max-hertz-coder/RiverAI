# common/redis_utils.py
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)
_client: aioredis.Redis | None = None

__all__ = [
    # базовое
    "init_redis_pool",
    "get_client",
    # контекст задач
    "set_task_context",
    "get_context_by_task_id",
    "cleanup_task_context",
    # совместимость со старым кодом
    "save_context",
    "get_task_context",
    # история чата
    "clear_conversation",
    "save_conversation",
    "get_conversation",
    # работа с «последним файлом решений» (некоторые модули бота их импортируют)
    "save_last_solutions_file",
    "get_last_solutions_file",
    "clear_last_solutions_file",
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

# ======================== последний файл решений ========================
# Некоторые обработчики бота (например, rabbit.py / homework_check / генерация решений)
# хранят в Redis «последний PDF/файл с решениями» для дальнейшего повторного скачивания.
# Мы поддерживаем два варианта ключей:
#   1) по task_id:        solutions:file:{task_id}
#   2) по user+student:   solutions:file:{user_id}:{student_id}

def _solutions_key_by_task(task_id: str) -> str:
    return f"solutions:file:{task_id}"

def _solutions_key_by_user(user_id: int, student_id: int) -> str:
    return f"solutions:file:{user_id}:{student_id}"

async def save_last_solutions_file(
    file_b64: str | bytes,
    *,
    task_id: Optional[str] = None,
    user_id: Optional[int] = None,
    student_id: Optional[int] = None,
    ttl_sec: int = 24 * 3600,
) -> None:
    """
    Универсальное сохранение «последнего файла решений».
    Приоритет ключа:
       1) task_id (если задан)
       2) user_id + student_id (оба обязательны)
    file_b64 — ожидается base64-строка. Если передан bytes — попытаемся декодировать в ascii/utf-8.
    """
    if isinstance(file_b64, bytes):
        try:
            file_b64 = file_b64.decode("ascii")
        except Exception:
            file_b64 = base64.b64encode(file_b64).decode("ascii")

    if not isinstance(file_b64, str) or not file_b64:
        raise ValueError("file_b64 must be a non-empty base64 string")

    c = _get_client()

    if task_id:
        await c.set(_solutions_key_by_task(task_id), file_b64, ex=ttl_sec)
        return

    if user_id is not None and student_id is not None:
        await c.set(_solutions_key_by_user(user_id, student_id), file_b64, ex=ttl_sec)
        return

    raise ValueError("Either task_id or (user_id and student_id) must be provided")

async def get_last_solutions_file(
    *,
    task_id: Optional[str] = None,
    user_id: Optional[int] = None,
    student_id: Optional[int] = None,
) -> Optional[str]:
    """
    Получить «последний файл решений»:
      - сначала по task_id (если задан),
      - иначе по паре user_id+student_id.
    Возвращает base64-строку или None.
    """
    c = _get_client()

    if task_id:
        raw = await c.get(_solutions_key_by_task(task_id))
        if raw:
            return raw

    if user_id is not None and student_id is not None:
        raw = await c.get(_solutions_key_by_user(user_id, student_id))
        if raw:
            return raw

    return None

async def clear_last_solutions_file(
    *,
    task_id: Optional[str] = None,
    user_id: Optional[int] = None,
    student_id: Optional[int] = None,
) -> None:
    """
    Удалить сохранённый файл решений (по task_id или по паре user_id+student_id).
    """
    c = _get_client()
    keys: list[str] = []
    if task_id:
        keys.append(_solutions_key_by_task(task_id))
    if user_id is not None and student_id is not None:
        keys.append(_solutions_key_by_user(user_id, student_id))
    if keys:
        await c.delete(*keys)
