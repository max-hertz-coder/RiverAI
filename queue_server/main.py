import asyncio
import logging
import os
from contextlib import suppress

import aio_pika

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

TASK_QUEUE = os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")
RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

# Опционально: TTL сообщений и префетч
TASK_TTL_MS = int(os.getenv("TASK_TTL_MS", "900000"))       # 15 минут
RESULT_TTL_MS = int(os.getenv("RESULT_TTL_MS", "900000"))   # 15 минут
PREFETCH_COUNT = int(os.getenv("PREFETCH_COUNT", "32"))


async def _declare_topology(channel: aio_pika.Channel) -> None:
    """
    Объявляет очереди и применяет базовые аргументы (durable, TTL).
    """
    # Префетч для всех консюмеров, которые будут открыты через этот канал
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)

    # Очередь задач
    await channel.declare_queue(
        TASK_QUEUE,
        durable=True,
        arguments={"x-message-ttl": TASK_TTL_MS},
    )
    # Очередь результатов
    await channel.declare_queue(
        RESULT_QUEUE,
        durable=True,
        arguments={"x-message-ttl": RESULT_TTL_MS},
    )
    logging.info("✅ RabbitMQ topology ready: %s / %s", TASK_QUEUE, RESULT_QUEUE)


async def main():
    logging.info("🚀 queue-server starting…")
    # ждём, пока брокер полностью поднимется (в docker-compose это часто нужно)
    await asyncio.sleep(3)

    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASS,
        virtualhost=RABBITMQ_VHOST,
        timeout=10,
        reconnect_interval=5,
    )
    logging.info("✅ Connected to RabbitMQ %s:%s vhost=%s", RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_VHOST)

    # Держим один канал для декларации топологии и health-пинга
    channel = await connection.channel()
    await _declare_topology(channel)

    # Периодический пинг, чтобы сервис был «живым» и писал в логи
    async def heartbeat():
        while True:
            try:
                await connection.ready()  # бросит исключение, если соединение упало
                logging.debug("❤️  queue-server heartbeat ok")
            except Exception as e:
                logging.warning("⚠️ heartbeat issue: %s", e)
            await asyncio.sleep(30)

    hb_task = asyncio.create_task(heartbeat(), name="heartbeat")

    try:
        await asyncio.Future()  # keep process alive
    finally:
        hb_task.cancel()
        with suppress(asyncio.CancelledError):
            await hb_task
        await channel.close()
        await connection.close()
        logging.info("🔌 queue-server stopped")


if __name__ == "__main__":
    asyncio.run(main())
