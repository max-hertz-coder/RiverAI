import asyncio
import logging
import json
import os

import aio_pika

from worker import config, db
from common.redis_utils import init_redis_pool
from worker.consumers import task_consumer

def _int(v, d):
    try:
        return int(v)
    except Exception:
        return d

def _get_db_dsn() -> str:
    """
    DSN воркера: сначала WORKER_POSTGRES_DSN, иначе собираем из POSTGRES_*.
    Не рушимся, если каких-то атрибутов нет в config — берём из окружения.
    """
    dsn = os.getenv("WORKER_POSTGRES_DSN", getattr(config, "WORKER_POSTGRES_DSN", "")) or ""
    if dsn:
        return dsn

    host = getattr(config, "DB_HOST", getattr(config, "POSTGRES_HOST", os.getenv("POSTGRES_HOST", "localhost")))
    port = _int(getattr(config, "DB_PORT", getattr(config, "POSTGRES_PORT", os.getenv("POSTGRES_PORT", "5432"))), 5432)
    name = getattr(config, "DB_NAME", getattr(config, "POSTGRES_DB", os.getenv("POSTGRES_DB", "riverai_db")))
    user = getattr(config, "DB_USER", getattr(config, "POSTGRES_USER", os.getenv("POSTGRES_USER", "riverai_user")))
    pwd = getattr(config, "DB_PASSWORD", getattr(config, "POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", "")))

    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"

async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        # 1) распаковываем задачу
        try:
            task_data = json.loads(message.body)
            logging.info(f"🔧 Получена задача: {task_data}")
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type = task_data.get("type")
        task_id = task_data.get("task_id")
        logging.info(f"▶ Received task: type={task_type}, task_id={task_id}")

        # 2) обрабатываем
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Task processed: type={task_type}, result_type={getattr(result, 'type', None)}")
        except Exception as e:
            logging.exception(f"🔴 Error processing task type={task_type}: {e}")
            return

        if not result:
            logging.warning("⚠️ Handler returned None — skipping")
            return

        # 3) сохраняем в Redis
        try:
            result["task_id"] = task_id
            logging.info(f"📤 Сохраняем результат в Redis (task_id={task_id}, type={result.get('type')})")

            from common.redis_utils import _get_client
            client = _get_client()
            result_key = f"result:{task_id}"
            await client.set(result_key, json.dumps(result), ex=3600)
            logging.info("📤 Result saved to Redis")
        except Exception as e:
            logging.exception(f"🔴 Error saving result to Redis: {e}")

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

    # 1) Redis
    r_host = getattr(config, "REDIS_HOST", os.getenv("REDIS_HOST", "redis"))
    r_port = _int(getattr(config, "REDIS_PORT", os.getenv("REDIS_PORT", "6379")), 6379)
    # у воркера обычно используем кэшный DB, если нет REDIS_DB — берём REDIS_DB_CACHE или 1
    r_db = _int(getattr(config, "REDIS_DB", getattr(config, "REDIS_DB_CACHE", os.getenv("REDIS_DB_CACHE", "1"))), 1)
    logging.info(f"🔧 Инициализация Redis: {r_host}:{r_port}/{r_db}")
    await init_redis_pool(r_host, r_port, r_db)

    # 2) Postgres
    dsn = _get_db_dsn()
    logging.info("🔧 Инициализация PostgreSQL…")
    await db.init_db_pool(dsn)

    # 3) RabbitMQ
    mq_host = getattr(config, "RABBITMQ_HOST", os.getenv("RABBITMQ_HOST", "rabbitmq"))
    mq_port = _int(getattr(config, "RABBITMQ_PORT", os.getenv("RABBITMQ_PORT", "5672")), 5672)
    mq_user = getattr(config, "RABBITMQ_USER", os.getenv("RABBITMQ_USER", "guest"))
    mq_pass = getattr(config, "RABBITMQ_PASS", os.getenv("RABBITMQ_PASS", "guest"))
    task_queue = getattr(config, "TASK_QUEUE", getattr(config, "RABBITMQ_TASK_QUEUE", os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")))
    logging.info(f"🔧 Подключение к RabbitMQ: {mq_host}:{mq_port}")

    # Устанавливаем увеличенный интервал heartbeat, чтобы соединение не рвалось во время долгих задач
    connection = await aio_pika.connect_robust(
        host=mq_host,
        port=mq_port,
        login=mq_user,
        password=mq_pass,
        heartbeat=120  # Увеличенный heartbeat (120 сек) для предотвращения разрыва соединения
    )
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    # ВАЖНО: не ломаем TTL — сначала пробуем пассивно открыть, а если нет — создаём с TTL
    ttl_ms = _int(os.getenv("RABBITMQ_TASK_TTL_MS", "900000"), 900000)
    try:
        await channel.declare_queue(task_queue, durable=True, passive=True)
        logging.info(f"✅ Подписались на существующую очередь '{task_queue}' (passive)")
    except Exception as e:
        logging.warning(f"⚠️ Passive declare '{task_queue}' не удался ({type(e).__name__}). Создаём с TTL={ttl_ms} мс…")
        await channel.declare_queue(task_queue, durable=True, arguments={"x-message-ttl": ttl_ms})

    queue = await channel.declare_queue(task_queue, durable=True, passive=True)
    await queue.consume(handle_message)
    logging.info(f"✅ Subscribed to '{task_queue}', awaiting tasks…")

    # 4) держим процесс живым
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
