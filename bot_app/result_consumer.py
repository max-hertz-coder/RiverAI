### ✅ НОВЫЙ ФАЙЛ: bot_app/result_consumer.py

import asyncio
import logging
from aio_pika import connect_robust
from aiogram import Bot
from bot_app.rabbit import process_result

bot = Bot(token="YOUR_TOKEN")  # Замените на ваш токен

async def consume_results():
    connection = await connect_robust("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    queue = await channel.declare_queue("result_queue", durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await process_result(message, bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(consume_results())