import asyncio
import logging
import json
import os

import aio_pika

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Чтение конфигурации из переменных окружения
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")


async def process_result(message: aio_pika.IncomingMessage):
    """
    Обработка сообщений из очереди result_queue: логируем и передаём основному боту.
    """
    async with message.process():
        try:
            raw = message.body.decode()
            data = json.loads(raw)
            logging.info(f"✅ Получен результат из '{RABBITMQ_RESULT_QUEUE}': {json.dumps(data, ensure_ascii=False)}")
            # TODO: здесь вызвать HTTP API основного бота или записать в Redis под ключ, откуда основной бот прочитает
        except Exception as e:
            logging.error(f"❌ Ошибка обработки сообщения: {e}")


async def main():
    # Задержка старта, чтобы RabbitMQ успел полностью подняться
    await asyncio.sleep(10)
    logging.info("🚀 Запуск queue-server. Подключаемся к RabbitMQ...")

    # Подключение к RabbitMQ с авто-переподключением каждые 5 секунд
    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASS,
        reconnect_interval=5,
    )
    logging.info("✅ Установлено соединение с RabbitMQ")

    channel = await connection.channel()
    queue = await channel.declare_queue(RABBITMQ_RESULT_QUEUE, durable=True)
    await queue.consume(process_result)
    logging.info(f"🔔 Подписаны на очередь '{RABBITMQ_RESULT_QUEUE}'")

    # Держим приложение активным
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⛔ Остановка queue-server")
