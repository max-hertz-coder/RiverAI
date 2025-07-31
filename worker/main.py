#!/usr/bin/env python3
import asyncio
import logging
import json

import aio_pika

from worker import config, db, redis_cache
from worker.consumers import task_consumer

async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        # 1) Распаковываем задачу
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type = task_data.get("type")
        task_id = task_data.get("task_id")
        logging.info(f"▶ Received task: type={task_type}, task_id={task_id}")

        # 2) Обрабатываем задачу
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Task processed: type={task_type}")
        except Exception:
            logging.exception(f"🔴 Error processing task type={task_type}")
            return

        if not result:
            logging.warning("⚠️ Handler returned None — skipping")
            return

        # 3) Отправляем результат в очередь
        try:
            # Добавляем task_id к результату
            result["task_id"] = task_id
            
            connection = await aio_pika.connect_robust(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                login=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASS,
            )
            channel = await connection.channel()
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(result).encode()),
                routing_key=config.RESULT_QUEUE
            )
            await connection.close()
            
            logging.info(f"📤 Result sent to queue: task_id={task_id}, type={result.get('type')}")

        except Exception:
            logging.exception("🔴 Error sending result to queue")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

    # 1) Инициализация PostgreSQL
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Инициализация Redis
    await redis_cache.init_redis_pool(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_DB)

    # 3) Подключение к RabbitMQ и подписка
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await queue.consume(handle_message)
    logging.info(f"✅ Subscribed to '{config.TASK_QUEUE}', awaiting tasks...")

    # 4) Не завершаемся
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())