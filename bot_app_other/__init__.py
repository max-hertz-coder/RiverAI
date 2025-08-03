import aio_pika
rabbit_channel: aio_pika.Channel | None = None  # Глобальный канал RabbitMQ (пока None)
