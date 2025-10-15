# worker/main.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import aio_pika

from common.redis_utils import init_redis_pool, _get_client
from worker import config
from worker.consumers import task_consumer
from worker import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

def _int(v: Any, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d

def _get_db_dsn() -> str:
    dsn = os.getenv("WORKER_POSTGRES_DSN", getattr(config, "WORKER_POSTGRES_DSN", "")) or ""
    if dsn:
        return dsn
    host = getattr(config, "DB_HOST", os.getenv("POSTGRES_HOST", "localhost"))
    port = _int(getattr(config, "DB_PORT", os.getenv("POSTGRES_PORT", "5432")), 5432)
    name = getattr(config, "DB_NAME", os.getenv("POSTGRES_DB", "riverai_db"))
    user = getattr(config, "DB_USER", os.getenv("POSTGRES_USER", "riverai_user"))
    pwd  = getattr(config, "DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"

async def _handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body)
        except Exception as e:
            logger.error("🔴 JSON decode error: %s", e)
            return
        task_id = payload.get("task_id")
        ttype = payload.get("type")
        logger.info("📥 Task received: id=%s type=%s", task_id, ttype)

        try:
            result = await task_consumer.process_task_message(payload)
        except Exception as e:
            logger.exception("🔴 Task processing error: %s", e)
            return

        if not result:
            logger.warning("⚠️ Empty result, skip")
            return

        try:
            result["task_id"] = task_id
            key = f"result:{task_id}"
            client = _get_client()
            await client.set(key, json.dumps(result, ensure_ascii=False), ex=3600)
            logger.info("📤 Result stored to Redis: %s", key)
        except Exception as e:
            logger.exception("🔴 Failed to store result in Redis: %s", e)

async def _connect_rabbitmq_with_retry() -> aio_pika.RobustChannel:
    host = getattr(config, "RABBITMQ_HOST", os.getenv("RABBITMQ_HOST", "rabbitmq"))
    port = _int(getattr(config, "RABBITMQ_PORT", os.getenv("RABBITMQ_PORT", "5672")), 5672)
    user = getattr(config, "RABBITMQ_USER", os.getenv("RABBITMQ_USER", "guest"))
    pwd  = getattr(config, "RABBITMQ_PASS", os.getenv("RABBITMQ_PASS", "guest"))

    delay = 1.0
    while True:
        try:
            logger.info("🔌 Connecting RabbitMQ %s:%s ...", host, port)
            conn = await aio_pika.connect_robust(
                host=host, port=port, login=user, password=pwd,
                heartbeat=30,          # чаще beat → меньше шанс таймаута на сервере (60s)
                timeout=10,
                client_properties={"connection_name": "riverai-worker"}
            )
            ch = await conn.channel()
            await ch.set_qos(prefetch_count=1)
            logger.info("✅ RabbitMQ connected")
            return ch
        except Exception as e:
            logger.warning("⚠️ RabbitMQ connect failed: %s; retrying ...", e)
            await asyncio.sleep(min(delay, 10.0))
            delay *= 1.6

async def main() -> None:
    # 1) Redis (устойчивые ретраи внутри init_redis_pool)
    r_host = getattr(config, "REDIS_HOST", os.getenv("REDIS_HOST", "redis"))
    r_port = _int(getattr(config, "REDIS_PORT", os.getenv("REDIS_PORT", "6379")), 6379)
    r_db   = _int(getattr(config, "REDIS_DB", getattr(config, "REDIS_DB_CACHE", os.getenv("REDIS_DB_CACHE", "1"))), 1)
    logger.info("🔧 Инициализация Redis: %s:%s/%s", r_host, r_port, r_db)
    await init_redis_pool(r_host, r_port, r_db)

    # 2) PostgreSQL
    dsn = _get_db_dsn()
    logger.info("🔧 Init PostgreSQL pool")
    await db.init_db_pool(dsn)

    # 3) RabbitMQ
    task_queue = getattr(config, "TASK_QUEUE", getattr(config, "RABBITMQ_TASK_QUEUE", os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")))
    channel = await _connect_rabbitmq_with_retry()

    # объявление очереди (passive → если нет, создадим)
    try:
        await channel.declare_queue(task_queue, durable=True, passive=True)
        logger.info("✅ Attached to existing queue '%s'", task_queue)
    except Exception:
        ttl_ms = _int(os.getenv("RABBITMQ_TASK_TTL_MS", "900000"), 900000)
        await channel.declare_queue(task_queue, durable=True, arguments={"x-message-ttl": ttl_ms})
        logger.info("ℹ️ Created queue '%s' with TTL=%d ms", task_queue, ttl_ms)

    queue = await channel.declare_queue(task_queue, durable=True, passive=True)
    await queue.consume(_handle_message)
    logger.info("🚀 Worker is running, waiting for tasks...")

    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
