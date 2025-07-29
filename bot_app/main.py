#!/usr/bin/env python3
import asyncio
import logging
import aio_pika
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from bot_app import config
from bot_app.database import db
from worker import redis_cache
from bot_app.rabbit import process_result
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers.start import router as start_router
from bot_app.handlers.students import router as students_router
from bot_app.handlers.ocr_and_generate import router as ocr_and_generate_router
from bot_app.handlers.generation import router as generation_router
from bot_app.handlers.chatgpt import router as chatgpt_router
from bot_app.handlers.subscription import router as subscription_router
from bot_app.handlers.settings import router as settings_router

async def consume_results(bot: Bot):
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=5)
    queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await process_result(message, bot)
            except Exception as e:
                logging.error(f"Ошибка обработки result_queue: {e}")

async def on_startup(bot_: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: удаляем старые команды и инициализируем службы")

    # Удаляем старые команды
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="en")
    await bot_.delete_my_commands(scope=None)

    # Устанавливаем новые команды
    await bot_.set_my_commands([
        BotCommand("start", "Старт бота"),
        BotCommand("back", "Завершить чат с GPT"),
    ], language_code="ru")
    await bot_.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("back", "End chat with GPT"),
    ], language_code="en")

    # Инициализация Redis для сохранения raw_tasks
    await redis_cache.init_redis_pool(
        config.REDIS_HOST,
        config.REDIS_PORT,
        config.REDIS_DB
    )

    # Запускаем фоновый таск обработки результатов
    asyncio.create_task(consume_results(bot_))

async def on_shutdown(bot_: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # Инициализация БД
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)

    # Настройка бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
    )
    dp = Dispatcher(storage=storage)

    # Подключаем middlewares и роутеры
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(start_router)
    dp.include_router(students_router)
    dp.include_router(ocr_and_generate_router)
    dp.include_router(generation_router)
    dp.include_router(chatgpt_router)
    dp.include_router(subscription_router)
    dp.include_router(settings_router)

    # Запуск поллинга
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )

if __name__ == "__main__":
    asyncio.run(main())