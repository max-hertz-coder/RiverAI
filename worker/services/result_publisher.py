import json
import logging
from aio_pika import connect_robust, Message

logger = logging.getLogger(__name__)

async def publish_result(result: dict):
    try:
        connection = await connect_robust("amqp://guest:guest@rabbitmq/")
        channel = await connection.channel()
        await channel.default_exchange.publish(
            Message(body=json.dumps(result).encode()),
            routing_key="result_queue"
        )
        await connection.close()
        logger.info(f"📤 Результат отправлен в очередь: task_id={result.get('task_id')}")
    except Exception as e:
        logger.exception(f"🔴 Ошибка отправки результата: {e}")