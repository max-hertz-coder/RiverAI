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
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers.start import router as start_router
from bot_app.handlers.students import router as students_router
from bot_app.handlers.ocr_and_generate import router as ocrgen_router
from bot_app.handlers.generation import router as gen_router
from bot_app.handlers.chatgpt import router as chatgpt_router
from bot_app.handlers.subscription import router as subscription_router
from bot_app.handlers.settings import router as settings_router
from bot_app.rabbit import process_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

async def consume_results(bot: Bot):
    conn = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=5)
    queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True)

    async with queue.iterator() as it:
        async for message in it:
            async with message.process():
                try:
                    await process_result(message, bot)
                except Exception:
                    logging.exception("Ошибка обработки сообщения из result_queue")

async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: сброс и установка команд бота")
    # Сброс всех команд
    await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
    await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="en")
    # Установка команд
    await bot.set_my_commands([
        BotCommand("start", "Старт бота"),
        BotCommand("back",  "Завершить чат с GPT"),
    ], scope=BotCommandScopeDefault(), language_code="ru")
    await bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("back",  "End chat with GPT"),
    ], scope=BotCommandScopeDefault(), language_code="en")

    # Запускаем слушатель result_queue
    asyncio.create_task(consume_results(bot))

async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()

async def main():
    # 1) Инициализация БД
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)

    # 2) Настройка бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp  = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 3) Роутеры
    dp.include_router(start_router)
    dp.include_router(students_router)
    dp.include_router(ocrgen_router)
    dp.include_router(gen_router)
    dp.include_router(chatgpt_router)
    dp.include_router(subscription_router)
    dp.include_router(settings_router)

    # 4) Старт polling
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )

if __name__ == "__main__":
    asyncio.run(main())