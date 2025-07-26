import asyncio
import logging
import json
import aio_pika
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Чтение конфигурации из переменных окружения
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")


def init_rabbitmq_connection(max_retries: int = 10, delay: int = 5) -> aio_pika.RobustConnection:
    """
    Пытается подключиться к RabbitMQ с повторными попытками.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🐇 Попытка {attempt}/{max_retries} подключения к RabbitMQ...")
            return asyncio.get_event_loop().run_until_complete(
                aio_pika.connect_robust(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    login=RABBITMQ_USER,
                    password=RABBITMQ_PASS,
                )
            )
        except Exception as e:
            logging.warning(f"❌ Ошибка подключения к RabbitMQ: {e}")
            if attempt < max_retries:
                logging.info(f"⏳ Ждём {delay} секунд перед следующей попыткой...")
                asyncio.sleep(delay)
    raise ConnectionError("🛑 Не удалось подключиться к RabbitMQ после нескольких попыток.")


async def process_result(message: aio_pika.IncomingMessage):
    """
    Обработка сообщений из очереди result_queue: логируем и сохраняем для основного бота.
    """
    async with message.process():
        try:
            body = message.body.decode()
            data = json.loads(body)
            logging.info(f"✅ Получен результат из {RABBITMQ_RESULT_QUEUE}: {json.dumps(data, ensure_ascii=False)}")
            # TODO: здесь вызвать HTTP API основного бота или сохранить результат в Redis/БД
        except Exception as e:
            logging.error(f"❌ Ошибка обработки сообщения: {e}")


async def main():
    logging.info("🚀 Запуск queue-server...")

    # Подключение к RabbitMQ с retry
    for attempt in range(1, 11):
        try:
            connection = await aio_pika.connect_robust(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                login=RABBITMQ_USER,
                password=RABBITMQ_PASS,
            )
            logging.info("✅ Успешно подключились к RabbitMQ")
            break
        except Exception as e:
            logging.warning(f"❌ Попытка {attempt} не удалась: {e}")
            await asyncio.sleep(5)
    else:
        logging.error("🛑 Не удалось подключиться к RabbitMQ, выходим.")
        return

    channel = await connection.channel()
    queue = await channel.declare_queue(RABBITMQ_RESULT_QUEUE, durable=True)
    await queue.consume(process_result)
    logging.info(f"🔔 Подписались на очередь {RABBITMQ_RESULT_QUEUE}")

    # Держим приложение активным
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logging.info("⛔ Остановка queue-server...")


if __name__ == "__main__":
    asyncio.run(main())
