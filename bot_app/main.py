#!/usr/bin/env python3
import asyncio
import logging
import aio_pika
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

import bot_app
from bot_app import config
from bot_app.database import db
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers import start, students, generation, chatgpt, subscription, settings
from bot_app.rabbit import process_result  # обработчик результата

bot: Bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

async def consume_results():
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=5)

    queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await process_result(message, bot)
            except Exception as e:
                logging.error(f"Ошибка обработки сообщения из result_queue: {e}")

async def on_startup(bot_: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: регистрация команд и запуск очереди")

    await bot_.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student", "➕ Добавить ученика"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("subscription", "💳 Оплата"),
    ])

    asyncio.create_task(consume_results())  # Фоновая подписка на очередь

async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    dp = Dispatcher(storage=RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
    ))

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )

if __name__ == "__main__":
    asyncio.run(main())
