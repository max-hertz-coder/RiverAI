import asyncio, os, json
from dotenv import load_dotenv
from loguru import logger
import sentry_sdk
import aio_pika

# Загрузка конфигурации из .env (RabbitMQ URL, Redis не используется здесь)
load_dotenv()
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
SENTRY_DSN = os.getenv("SENTRY_DSN")

# Логирование для воркера
logger.add("worker.log", rotation="1 MB", level="INFO")
logger.info("Starting queue_server worker...")
# Инициализация Sentry (если задан DSN)
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=True)
    logger.info("Sentry SDK initialized for worker")

async def main():
    # Подключаемся к RabbitMQ
    logger.info("Connecting to RabbitMQ broker...")
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    # Объявляем (убеждаемся, что существуют) очереди
    task_queue = await channel.declare_queue("task_queue", durable=True)
    result_queue = await channel.declare_queue("result_queue", durable=True)
    # Устанавливаем prefetch=1 (один воркер берет одно сообщение за раз)
    await channel.set_qos(prefetch_count=1)
    logger.info("Connected to RabbitMQ (vhost /riverai), waiting for tasks...")

    # Функция обработки входящих задач из task_queue
    async def process_task(message: aio_pika.IncomingMessage):
        async with message.process():  # автоматически отправит ack после выполнения блока
            try:
                data = json.loads(message.body.decode())
                chat_id = data.get("chat_id")
                user_request = data.get("request", "")
                logger.info(f"Received task for chat {chat_id}: {user_request}")
                # Имитация генерации упражнения (бизнес-логика):
                # Например, на основе темы и сложности формируем текст.
                result_text = generate_exercise_stub(user_request)
                # Отправляем результат обратно в очередь результатов
                result_payload = {"chat_id": chat_id, "result": result_text}
                await channel.default_exchange.publish(
                    aio_pika.Message(body=json.dumps(result_payload).encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key="result_queue"
                )
                logger.info(f"Task completed for chat {chat_id}, result sent to result_queue")
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                # При исключении контекстный менеджер не подтвердит сообщение (можно сделать message.nack())
                # Здесь можно реализовать повторную постановку или специальные обработки ошибок.

    # Помощник: простая заглушка генерации упражнения
    def generate_exercise_stub(request: str) -> str:
        """
        Генерирует фиктивное упражнение на основе запроса.
        В реальности здесь мог быть вызов OpenAI или другой долгий расчёт.
        """
        # В качестве примера - просто возвращаем шаблонный текст с запросом
        return f"**Упражнение по запросу:** {request}\n1. Вопрос: ...?\n2. Вопрос: ...?\nОтветы: ..."

    # Подписываемся на очередь задач (consumer)
    await task_queue.consume(process_task)
    logger.info("Worker is now consuming tasks from task_queue...")
    # Блокируем выполнение чтобы воркер работал вечно
    await asyncio.Future()  # держим main() запущенным
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Worker stopped!")
