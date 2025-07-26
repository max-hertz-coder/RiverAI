import asyncio
import logging
import json
import aio_pika
import os

logging.basicConfig(level=logging.INFO)

# Загружаем конфиг из переменных окружения
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")


async def process_result(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            body = message.body.decode()
            data = json.loads(body)
            logging.info(f"✅ Получен результат из result_queue:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
            
            # 👉 здесь можно: 
            # - отправлять результат в основной бот через HTTP
            # - сохранять в Redis или БД
            # - логировать в файл и т.п.

        except Exception as e:
            logging.error(f"❌ Ошибка при обработке сообщения: {e}")


async def main():
    logging.info("🚀 Запуск queue-server...")

    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASS,
    )
    channel = await connection.channel()

    queue = await channel.declare_queue(RABBITMQ_RESULT_QUEUE, durable=True)
    await queue.consume(process_result)

    logging.info(f"🔔 Подписка на очередь {RABBITMQ_RESULT_QUEUE} активирована")

    while True:
        await asyncio.sleep(3600)  # Бесконечное ожидание

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⛔ Остановка queue-server")
