# bot_app/broker.py
import logging
from typing import Awaitable, Callable, Optional

import aio_pika
from aio_pika import Message, DeliveryMode, IncomingMessage

from bot_app import config

logger = logging.getLogger(__name__)


class RabbitBroker:
    """Робастная обёртка над aio-pika с едиными именами очередей из config."""

    def __init__(self) -> None:
        self._conn: Optional[aio_pika.RobustConnection] = None
        self._ch: Optional[aio_pika.abc.AbstractChannel] = None
        self._task_q: Optional[aio_pika.abc.AbstractQueue] = None
        self._result_q: Optional[aio_pika.abc.AbstractQueue] = None

        self._amqp_url = config.RABBITMQ_AMQP_URL()
        self._task_queue_name = config.TASK_QUEUE
        self._result_queue_name = config.RESULT_QUEUE

    async def connect(self) -> None:
        logger.info("🔌 Connecting to RabbitMQ… %s", self._amqp_url)
        self._conn = await aio_pika.connect_robust(self._amqp_url)
        self._ch = await self._conn.channel()
        await self._ch.set_qos(prefetch_count=4)

        self._task_q = await self._ch.declare_queue(self._task_queue_name, durable=True)
        self._result_q = await self._ch.declare_queue(self._result_queue_name, durable=True)
        logger.info("✅ RabbitMQ connected. Queues declared: %s, %s",
                    self._task_queue_name, self._result_queue_name)

    async def publish_task(self, body: bytes) -> None:
        if not self._ch:
            raise RuntimeError("Channel is not initialized. Call connect() first.")
        msg = Message(body, delivery_mode=DeliveryMode.PERSISTENT)
        await self._ch.default_exchange.publish(msg, routing_key=self._task_queue_name)
        logger.debug("➡️ Task published to %s", self._task_queue_name)

    async def publish_result(self, body: bytes) -> None:
        if not self._ch:
            raise RuntimeError("Channel is not initialized. Call connect() first.")
        msg = Message(body, delivery_mode=DeliveryMode.PERSISTENT)
        await self._ch.default_exchange.publish(msg, routing_key=self._result_queue_name)
        logger.debug("➡️ Result published to %s", self._result_queue_name)

    async def consume_tasks(self, callback: Callable[[IncomingMessage], Awaitable[None]]) -> None:
        if not self._task_q:
            raise RuntimeError("Task queue is not initialized. Call connect() first.")
        logger.info("👂 Consuming tasks from %s", self._task_queue_name)
        await self._task_q.consume(callback, no_ack=False)

    async def consume_results(self, callback: Callable[[IncomingMessage], Awaitable[None]]) -> None:
        if not self._result_q:
            raise RuntimeError("Result queue is not initialized. Call connect() first.")
        logger.info("👂 Consuming results from %s", self._result_queue_name)
        await self._result_q.consume(callback, no_ack=False)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("🔌 RabbitMQ connection closed.")
