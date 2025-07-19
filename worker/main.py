#!/usr/bin/env python3
import asyncio
import logging
import json

import aio_pika
from aio_pika import Message, IncomingMessage

from worker import config, db, redis_cache
from worker.consumers import task_consumer

# Global reference to the default exchange for publishing results
publish_exchange: aio_pika.Exchange | None = None

async def handle_message(message: IncomingMessage) -> None:
    async with message.process():
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type = task_data.get("type")
        logging.info(f"▶ Received task of type: {task_type}")

        # Dispatch to the appropriate service
        try:
            result = await task_consumer.process_task_message(task_data)
        except Exception:
            logging.exception("🔴 Error while processing task")
            return

        if not result:
            logging.warning("⚠️ No result returned by task_consumer")
            return

        if publish_exchange is None:
            logging.error("🔴 Cannot publish result: publish_exchange is not initialized")
            return

        # Publish the result back to the result queue
        try:
            await publish_exchange.publish(
                Message(body=json.dumps(result).encode("utf-8")),
                routing_key=config.RESULT_QUEUE,
            )
            logging.info("✅ Published result to result queue")
        except Exception:
            logging.exception("🔴 Failed to publish result")

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.info("🚀 Worker starting up")

    # 1) Initialize PostgreSQL pool via DSN
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Database pool initialized")

    # 2) Initialize Redis cache (for chat context, etc.)
    await redis_cache.init_redis()
    logging.info("✔️ Redis cache initialized")

    # 3) Connect to RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    logging.info("✔️ Connected to RabbitMQ")

    # 4) Grab the default exchange for publishing results
    global publish_exchange
    publish_exchange = channel.default_exchange

    # 5) Declare both the task and result queues (idempotent)
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.declare_queue(config.RESULT_QUEUE, durable=True)
    logging.info(f"🕸 Queues declared: {config.TASK_QUEUE}, {config.RESULT_QUEUE}")

    # 6) Subscribe to the task queue
    task_queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    await task_queue.consume(handle_message)
    logging.info(f"✅ Subscribed to '{config.TASK_QUEUE}', waiting for tasks…")

    # 7) Keep the process alive indefinitely
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
