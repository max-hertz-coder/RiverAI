import json
import aio_pika
from bot_app import config
from bot_app.utils.task_utils import create_task_with_context

async def enqueue_generate_plan(user_id: int, student_id: int, description: str):
    task = {
        "type": "generate_plan",
        "user_id": user_id,
        "student_id": student_id,
        "description": description
    }

    # Создаем задачу с контекстом
    task_with_context = await create_task_with_context(task)
    task_id = task_with_context["task_id"]

    # Лог задачи
    print(f"[BOT_APP] 🔄 Отправка задачи в Worker: task_id={task_id}, user_id={user_id}")

    message_body = json.dumps(task_with_context).encode()

    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.default_exchange.publish(
        aio_pika.Message(body=message_body),
        routing_key=config.TASK_QUEUE
    )
    await connection.close()