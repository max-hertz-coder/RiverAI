import asyncio
import logging
import json

import aio_pika

from worker import config, db, redis_cache
from worker.consumers import task_consumer

async def main():
    logging.basicConfig(level=logging.INFO)
    # Initialize DB and Redis
    await db.init_db_pool()
    await redis_cache.init_redis()
    # Connect to RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    channel = await connection.channel()
    # Declare queues
    task_queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    result_exchange = await channel.declare_exchange("", aio_pika.ExchangeType.DIRECT)  # default exchange for direct publish
    # Consume tasks
    async for msg in task_queue:
        async with msg.process():
            try:
                task_data = msg.body.decode('utf-8')
            except Exception as e:
                logging.error(f"Failed to decode task message: {e}")
                continue
            result = await task_consumer.process_task_message(task_data)
            if result:
                # Publish result message to result_queue
                try:
                    await result_exchange.publish(
                        aio_pika.Message(body=json.dumps(result).encode('utf-8')),
                        routing_key=config.RESULT_QUEUE
                    )
                except Exception as e:
                    logging.error(f"Failed to publish result: {e}")

if __name__ == "__main__":
    asyncio.run(main())
