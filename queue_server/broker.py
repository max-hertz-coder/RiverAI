import aio_pika
import os

class RabbitBroker:
    def __init__(self):
        self.task_queue_name = os.getenv("TASK_QUEUE", "task_queue")
        self.result_queue_name = os.getenv("RESULT_QUEUE", "result_queue")
        self.host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        self.user = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASS", "guest")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.conn = None
        self.channel = None

    async def connect(self):
        self.conn = await aio_pika.connect_robust(
            host=self.host,
            login=self.user,
            password=self.password,
            port=self.port
        )
        self.channel = await self.conn.channel()
        # Создаём очереди
        await self.channel.declare_queue(self.task_queue_name, durable=True)
        await self.channel.declare_queue(self.result_queue_name, durable=True)

    async def publish_task(self, body: bytes):
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=body),
            routing_key=self.task_queue_name
        )

    async def consume_tasks(self, callback):
        queue = await self.channel.declare_queue(self.task_queue_name, durable=True)
        await queue.consume(callback)

    async def publish_result(self, body: bytes):
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=body),
            routing_key=self.result_queue_name
        )

    async def consume_results(self, callback):
        queue = await self.channel.declare_queue(self.result_queue_name, durable=True)
        await queue.consume(callback)
