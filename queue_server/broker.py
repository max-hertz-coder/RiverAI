import os
import logging
from typing import Callable, Awaitable

import aio_pika
from aio_pika import Message, DeliveryMode, IncomingMessage

logger = logging.getLogger(__name__)


class RabbitBroker:
    """
    Обёртка для подключения к RabbitMQ и работы с очередями задач и результатов.
    Все настройки берутся из переменных окружения:
      - RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASS
      - TASK_QUEUE, RESULT_QUEUE
    """

    def __init__(self):
        # Чтение конфигурации из env
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.user = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASS", "guest")
        self.task_queue_name = os.getenv("TASK_QUEUE", "task_queue")
        self.result_queue_name = os.getenv("RESULT_QUEUE", "result_queue")

        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._task_queue: aio_pika.abc.AbstractQueue | None = None
        self._result_queue: aio_pika.abc.AbstractQueue | None = None

    async def connect(self):
        """Устанавливает соединение и инициализирует очередь задач и результатов."""
        logger.info(f"Connecting to RabbitMQ at {self.host}:{self.port}...")
        self._connection = await aio_pika.connect_robust(
            host=self.host,
            port=self.port,
            login=self.user,
            password=self.password
        )
        self._channel = await self._connection.channel()
        # Опционально: ограничить число одновременно доставляемых сообщений
        await self._channel.set_qos(prefetch_count=1)

        # Объявляем (или получаем) очереди
        self._task_queue = await self._channel.declare_queue(
            self.task_queue_name, durable=True
        )
        self._result_queue = await self._channel.declare_queue(
            self.result_queue_name, durable=True
        )
        logger.info("RabbitMQ connection established, queues declared.")

    async def consume_tasks(
        self,
        callback: Callable[[IncomingMessage], Awaitable[None]]
    ):
        """
        Подписка на входящую очередь задач.
        callback — async-функция, принимающая IncomingMessage.
        """
        if not self._task_queue:
            raise RuntimeError("Task queue is not initialized. Call connect() first.")
        logger.info(f"Starting to consume tasks from '{self.task_queue_name}'...")
        await self._task_queue.consume(callback, no_ack=False)

    async def consume_results(
        self,
        callback: Callable[[IncomingMessage], Awaitable[None]]
    ):
        """
        Подписка на очередь результатов от воркеров.
        """
        if not self._result_queue:
            raise RuntimeError("Result queue is not initialized. Call connect() first.")
        logger.info(f"Starting to consume results from '{self.result_queue_name}'...")
        await self._result_queue.consume(callback, no_ack=False)

    async def publish_task(self, body: bytes):
        """
        Публикует задачу в очередь воркеров.
        """
        if not self._channel:
            raise RuntimeError("Channel is not initialized. Call connect() first.")
        message = Message(
            body,
            delivery_mode=DeliveryMode.PERSISTENT
        )
        await self._channel.default_exchange.publish(
            message,
            routing_key=self.task_queue_name
        )
        logger.debug(f"Published task to '{self.task_queue_name}'")

    async def publish_result(self, body: bytes):
        """
        Публикует результат обратно боту.
        """
        if not self._channel:
            raise RuntimeError("Channel is not initialized. Call connect() first.")
        message = Message(
            body,
            delivery_mode=DeliveryMode.PERSISTENT
        )
        await self._channel.default_exchange.publish(
            message,
            routing_key=self.result_queue_name
        )
        logger.debug(f"Published result to '{self.result_queue_name}'")

    async def close(self):
        """Закрывает соединение с RabbitMQ."""
        if self._connection:
            await self._connection.close()
            logger.info("RabbitMQ connection closed.")
