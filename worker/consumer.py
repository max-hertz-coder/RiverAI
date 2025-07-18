import asyncio
import json
import logging

import aio_pika
from bot_app import config
from worker.services.gpt_service import chat_with_gpt  # ваш сервис, обёртка OpenAI

async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body)
        t    = data.get("type")
        user = data.get("user_id")
        sid  = data.get("student_id")

        if t == "chat_gpt":
            prompt = data.get("message", "")
            try:
                answer = await chat_with_gpt(prompt)
                result = {
                    "type":       "chat",
                    "user_id":    user,
                    "student_id": sid,
                    "answer":     answer,
                }
            except Exception as e:
                logging.exception("Ошибка в chat_with_gpt:")
                result = {"type":"error","user_id":user,"message":"GPT error"}
        else:
            # Игнорируем другие типы, или добавьте сюда другие обработки
            return

        # Публикуем результат в очередь
        try:
            await message.channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(result).encode("utf-8")),
                routing_key=config.RABBITMQ_RESULT_QUEUE,
            )
        except Exception:
            logging.exception("Не удалось опубликовать результат в result_queue")

async def main():
    # 1) Подключаемся к RabbitMQ
    conn = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await conn.channel()
    # 2) Убеждаемся, что очереди существуют
    await channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    await channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)
    # 3) Подписываемся на задачи
    queue = await channel.get_queue(config.RABBITMQ_TASK_QUEUE)
    await queue.consume(process_message, no_ack=False)
    # 4) Ждём сообщений
    print("Worker запущен, ожидаем задачи...")
    await asyncio.Future()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())