import json
import aio_pika

from bot_app import config
from bot_app.utils.task_utils import create_task_with_context


async def enqueue_generate_plan(user_id: int, student_id: int, description: str):
    """
    Ставит задачу генерации учебного плана.
    Тип — 'plan' (совместим с worker.services.plan_service.handle_plan).
    """
    task = {
        "type": "plan",
        "user_id": user_id,
        "student_id": student_id,
        "description": description,
    }

    task_with_context = await create_task_with_context(task)
    body = json.dumps(task_with_context, ensure_ascii=False).encode("utf-8")

    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.default_exchange.publish(
        aio_pika.Message(body=body),
        routing_key=config.TASK_QUEUE,
    )
    await connection.close()
