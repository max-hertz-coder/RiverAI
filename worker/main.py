#!/usr/bin/env python3
import asyncio
import logging
import json

import aio_pika
from aio_pika import Message, IncomingMessage

from worker import config, db, redis_cache
from worker.consumers import task_consumer

# Global reference to the default exchange for publishing results
publish_exchange: aio_pika.Exchange | None = None

async def handle_message(message: IncomingMessage) -> None:
    async with message.process():
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type = task_data.get("type")
        user_id   = task_data.get("user_id")
        student_id = task_data.get("student_id")
        logging.info(f"▶ Получена задача: type={task_type}, user={user_id}, student={student_id}")

        # Выполняем задачу через нужный обработчик
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Задача type={task_type} успешно обработана.")
        except Exception as e:
            logging.exception(f"🔴 Ошибка при обработке задачи type={task_type}")
            return

        if not result:
            logging.warning("⚠️ process_task_message вернул None — результат не будет отправлен")
            return

        if publish_exchange is None:
            logging.error("🔴 publish_exchange is not initialized — невозможно отправить результат")
            return

        # Публикуем результат в очередь
        try:
            result_json = json.dumps(result, ensure_ascii=False)
            await publish_exchange.publish(
                Message(body=result_json.encode("utf-8")),
                routing_key=config.RESULT_QUEUE,
            )
            logging.info(f"📤 Результат опубликован в очередь '{config.RESULT_QUEUE}': {result_json}")
        except Exception:
            logging.exception("🔴 Ошибка при публикации результата в очередь")

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.info("🚀 Запуск воркера...")

    # 1) Подключаем БД
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Подключение к PostgreSQL успешно")

    # 2) Подключаем Redis
    await redis_cache.init_redis()
    logging.info("✔️ Подключение к Redis успешно")

    # 3) Подключение к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    logging.info("✔️ Подключение к RabbitMQ успешно")

    # 4) Сохраняем default exchange
    global publish_exchange
    publish_exchange = channel.default_exchange

    # 5) Объявляем очереди (на всякий случай)
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.declare_queue(config.RESULT_QUEUE, durable=True)
    logging.info(f"🕸 Очереди объявлены: {config.TASK_QUEUE}, {config.RESULT_QUEUE}")

    # 6) Подписка на очередь задач
    task_queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    await task_queue.consume(handle_message)
    logging.info(f"✅ Подписка на очередь '{config.TASK_QUEUE}' выполнена. Ожидаю задачи...")

    # 7) Бесконечный цикл
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
