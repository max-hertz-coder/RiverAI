#!/usr/bin/env python3
import asyncio
import logging
import json

import aio_pika
from aio_pika import Message

from worker import config, db, redis_cache
from worker.consumers import task_consumer

# Глобальная переменная для обмена (default exchange) RabbitMQ
publish_exchange: aio_pika.Exchange | None = None

async def handle_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        t = task_data.get("type")
        logging.info(f"▶ Received task of type: {t}")

        try:
            result = await task_consumer.process_task_message(task_data)
        except Exception:
            logging.exception("🔴 Error while processing task:")
            return

        if not result:
            logging.warning("⚠️ No result returned by task_consumer")
            return

        if publish_exchange is None:
            logging.error("🔴 Cannot publish result: publish_exchange is not initialized")
            return

        try:
            await publish_exchange.publish(
                Message(body=json.dumps(result).encode("utf-8")),
                routing_key=config.RESULT_QUEUE
            )
            logging.info("✅ Published result to result queue")
        except Exception:
            logging.exception("🔴 Failed to publish result:")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.info("🚀 Worker starting up")

    # 1) Инициализация PostgreSQL через DSN
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Database pool initialized")

    # 2) Инициализация Redis
    await redis_cache.init_redis()
    logging.info("✔️ Redis cache initialized")

    # 3) Подключение к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    logging.info("✔️ Connected to RabbitMQ")

    # Сохраняем default exchange из канала
    global publish_exchange
    publish_exchange = channel.default_exchange

    # 4) Объявляем очередь задач и подписываемся на неё
    task_queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    await task_queue.consume(handle_message)
    logging.info(f"✅ Subscribed to queue '{config.TASK_QUEUE}', waiting for tasks…")

    # 5) Блокировка, чтобы процесс не завершился
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
