#!/usr/bin/env python3
import asyncio
import logging
import aio_pika

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

import bot_app.config as app_config
import worker.config as worker_config
from common.redis_utils import init_redis_pool
from bot_app.database import db
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
        host=app_config.RABBITMQ_HOST,
        port=app_config.RABBITMQ_PORT,
        login=app_config.RABBITMQ_USER,
        password=app_config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=5)
    queue = await channel.declare_queue(app_config.RESULT_QUEUE, durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await process_result(message, bot)
            except Exception as e:
                logging.error(f"Ошибка обработки result_queue: {e}")


async def on_startup(bot_: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: очищаем команды и инициализируем сервисы")

    # Удаляем все старые команды
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="en")
    await bot_.delete_my_commands(scope=None)

    # Ставим новые команды
    await bot_.set_my_commands([
        BotCommand("start", "Старт бота"),
        BotCommand("back",  "Завершить чат с GPT"),
    ], language_code="ru")
    await bot_.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("back",  "End chat with GPT"),
    ], language_code="en")

    # Запускаем фоновую задачу обработки результатов из RabbitMQ
    asyncio.create_task(consume_results(bot_))


async def on_shutdown(bot_: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # 1) Инициализация Redis (должна быть первой!)
    await init_redis_pool(
        worker_config.REDIS_HOST,
        worker_config.REDIS_PORT,
        worker_config.REDIS_DB
    )

    # 2) Инициализация PostgreSQL
    dsn = (
        f"postgresql://{app_config.DB_USER}:{app_config.DB_PASSWORD}"
        f"@{app_config.DB_HOST}:{app_config.DB_PORT}/{app_config.DB_NAME}"
    )
    await db.init_db_pool(dsn)

    # 3) Настройка Bot и Dispatcher
    bot = Bot(
        token=app_config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage.from_url(
        f"redis://{worker_config.REDIS_HOST}:{worker_config.REDIS_PORT}/{app_config.REDIS_DB_FSM}"
    )
    dp = Dispatcher(storage=storage)

    # Подключаем middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Регистрируем роутеры
    dp.include_router(start_router)
    dp.include_router(students_router)
    dp.include_router(ocr_and_generate_router)
    dp.include_router(generation_router)
    dp.include_router(chatgpt_router)
    dp.include_router(subscription_router)
    dp.include_router(settings_router)
    

    # Запуск polling
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )


if __name__ == "__main__":
    asyncio.run(main())