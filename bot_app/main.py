#!/usr/bin/env python3
import asyncio
import logging
import aio_pika
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from bot_app import config
from bot_app.database import db
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers import start, students, generation, chatgpt, subscription, settings
from bot_app.rabbit import process_result  # импорт обработчика очереди

async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: регистрация команд и подключение к RabbitMQ")

    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student", "➕ Добавить ученика"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("subscription", "💳 Оплата"),
    ])

    # RabbitMQ подключение
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=5)

    # Очереди
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    result_q = await channel.declare_queue(config.RESULT_QUEUE, durable=True)

    # Подписка на очередь
    async def wrapped_result_callback(msg):
        await process_result(msg, bot)

    await result_q.consume(wrapped_result_callback)
    logging.info(f"📡 Subscribed to result queue '{config.RESULT_QUEUE}'")

async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

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
