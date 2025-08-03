import json
import logging
import aio_pika
from worker import config

logger = logging.getLogger(__name__)

async def publish_result(result: dict):
    try:
        logger.info(f"📤 Пытаемся отправить результат в RabbitMQ:")
        logger.info(f"  Host: {config.RABBITMQ_HOST}")
        logger.info(f"  Port: {config.RABBITMQ_PORT}")
        logger.info(f"  User: {config.RABBITMQ_USER}")
        logger.info(f"  Queue: {config.RESULT_QUEUE}")
        
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
        logger.info(f"📤 Результат отправлен в очередь: task_id={result.get('task_id')}")
    except Exception as e:
        logger.exception(f"🔴 Ошибка отправки результата: {e}")