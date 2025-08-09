import json
import logging
import aio_pika
from worker import config

logger = logging.getLogger(__name__)


async def publish_result(result: dict) -> None:
    """
    Публикует результат в RESULT_QUEUE (RabbitMQ).
    """
    try:
        task_id = result.get("task_id")
        logger.info("📤 Публикуем результат в RabbitMQ (task_id=%s, queue=%s)", task_id, config.RESULT_QUEUE)

        connection = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER,
            password=config.RABBITMQ_PASS,
        )
        channel = await connection.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(result).encode("utf-8")),
            routing_key=config.RESULT_QUEUE,
        )
        await connection.close()
        logger.info("✅ Результат отправлен (task_id=%s)", task_id)
    except Exception:
        logger.exception("🔴 Ошибка отправки результата в RabbitMQ")
