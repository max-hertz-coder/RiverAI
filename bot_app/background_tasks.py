import json
import uuid
from aio_pika import connect_robust, Message
from bot_app.redis_cache import redis

async def enqueue_generate_plan(user_id: int, student_id: int, description: str):
    task_id = str(uuid.uuid4())

    # Лог задачи
    print(f"[BOT_APP] 🔄 Отправка задачи в Worker: task_id={task_id}, user_id={user_id}")

    # Сохраняем mapping в Redis
    await redis.set(f"task_context:{task_id}", json.dumps({
        "user_id": user_id,
        "type": "generate_plan",
        "student_id": student_id,
        "description": description
    }), ex=3600)

    message_body = json.dumps({
        "task_id": task_id,
        "type": "generate_plan",
        "student_id": student_id,
        "description": description
    }).encode()

    connection = await connect_robust("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    await channel.default_exchange.publish(
        Message(body=message_body),
        routing_key="tasks_queue"
    )