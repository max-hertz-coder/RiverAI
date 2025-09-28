#!/usr/bin/env python3
import os
import asyncio
import logging
import contextlib

from aiohttp import web
from bot_app.webhooks.payment_webhook_aiohttp import build_app as build_payment_app

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from common.redis_utils import init_redis_pool
import bot_app.config as app_config

# DB
from bot_app.database import db

# Роутеры хэндлеров
from bot_app.handlers.start import router as start_router
from bot_app.handlers.students import router as students_router
from bot_app.handlers.ocr_and_generate import router as ocr_and_generate_router
from bot_app.handlers.generation import router as generation_router
from bot_app.handlers.chatgpt import router as chatgpt_router
from bot_app.handlers.subscription import router as subscription_router
from bot_app.handlers.settings import router as settings_router
from bot_app.handlers.homework_check import router as homework_check_router
from bot_app.handlers.main_menu import router as main_menu_router
from bot_app.handlers.payment import router as payment_router

# Результаты (AMQP + Redis)
from bot_app.result_consumer import run_result_consumers

# Middleware
from bot_app.middlewares.auth import AuthMiddleware

# RabbitMQ общий канал
import aio_pika
import bot_app  # чтобы положить connection/channel в пространство пакета


async def on_startup(bot_: Bot, dp: Dispatcher):
    logging.info("🚀 Startup: очищаем команды и инициализируем сервисы")

    # Сбрасываем команды (RU/EN)
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
    await bot_.delete_my_commands(scope=BotCommandScopeDefault(), language_code="en")
    await bot_.delete_my_commands(scope=None)

    await bot_.set_my_commands([
        BotCommand("start", "Старт бота"),
        BotCommand("help", "Помощь"),
    ], language_code="ru")
    await bot_.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("help", "Help"),
    ], language_code="en")

    logging.info("✅ Startup завершён")


async def on_shutdown(bot_: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем ресурсы")
    # Закрываем пул БД
    try:
        if db._pool:
            await db._pool.close()
            logging.info("🔌 DB pool закрыт")
    except Exception:
        logging.exception("Ошибка закрытия DB pool")

    # Закрываем RabbitMQ канал и соединение
    try:
        if getattr(bot_app, "rabbit_channel", None):
            await bot_app.rabbit_channel.close()
            logging.info("🔌 RabbitMQ канал закрыт")
    except Exception:
        logging.exception("Ошибка закрытия RabbitMQ канала")

    try:
        if getattr(bot_app, "rabbit_connection", None):
            await bot_app.rabbit_connection.close()
            logging.info("🔌 RabbitMQ соединение закрыто")
    except Exception:
        logging.exception("Ошибка закрытия RabbitMQ соединения")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    # 1) Redis
    await init_redis_pool(app_config.REDIS_HOST, app_config.REDIS_PORT, app_config.REDIS_DB_CACHE)

    # 2) PostgreSQL
    await db.init_db_pool(app_config.POSTGRES_DSN())

    # 3) Bot + Dispatcher
    bot = Bot(token=app_config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(f"redis://{app_config.REDIS_HOST}:{app_config.REDIS_PORT}/{app_config.REDIS_DB_FSM}")
    dp = Dispatcher(storage=storage)

    # 4) RabbitMQ канал
    logging.info("🔧 Инициализация RabbitMQ канала…")
    bot_app.rabbit_connection = await aio_pika.connect_robust(
        host=app_config.RABBITMQ_HOST,
        port=app_config.RABBITMQ_PORT,
        login=app_config.RABBITMQ_USER,
        password=app_config.RABBITMQ_PASS,
    )
    bot_app.rabbit_channel = await bot_app.rabbit_connection.channel()
    logging.info("✅ RabbitMQ канал инициализирован")

    # 5) Middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 6) Роутеры
    dp.include_router(start_router)
    dp.include_router(students_router)
    dp.include_router(ocr_and_generate_router)
    dp.include_router(generation_router)
    dp.include_router(chatgpt_router)
    dp.include_router(subscription_router)
    dp.include_router(settings_router)
    dp.include_router(homework_check_router)
    dp.include_router(main_menu_router)
    dp.include_router(payment_router)

    # 7) AIOHTTP: вебхук оплаты
    webhook_port = int(os.getenv("PAYMENT_WEBHOOK_PORT", "8080"))
    payment_app = build_payment_app()
    runner = web.AppRunner(payment_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", webhook_port)
    await site.start()
    logging.info("🌐 Payment webhook is listening on 0.0.0.0:%d", webhook_port)

    # 8) Консьюмеры результатов (AMQP + Redis)
    consumers_task = asyncio.create_task(run_result_consumers(bot), name="result_consumers")

    # 9) Запуск бота
    try:
        await dp.start_polling(bot, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
    finally:
        consumers_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumers_task
        with contextlib.suppress(Exception):
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
