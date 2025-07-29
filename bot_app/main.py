#!/usr/bin/env python3
import asyncio
import logging

import aio_pika
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot_app import config
from bot_app.database import db
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.rabbit import process_result

# Наши роутеры
from bot_app.handlers.start   import router as start_router
from bot_app.handlers.students import router as students_router
from bot_app.handlers.ocr_and_generate import router as ocrgen_router
from bot_app.handlers.generation      import router as gen_router
from bot_app.handlers.chatgpt         import router as chatgpt_router
from bot_app.handlers.subscription   import router as subscription_router
from bot_app.handlers.settings       import router as settings_router

# Настраиваем логгирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

async def consume_results(bot: Bot):
    """
    Слушаем result_queue и прокидываем результат в process_result.
    """
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
    logging.info("🚀 Startup: удаляем и обновляем команды бота")
    # Сбрасываем старые команды
    await bot.delete_my_commands(scope=None)
    # Ставим только нужные
    await bot.set_my_commands([
        ("start", "Старт бота"),
        ("back",  "Завершить чат с GPT"),
    ], scope=None, language_code="ru")
    await bot.set_my_commands([
        ("start", "Start bot"),
        ("back",  "End chat with GPT"),
    ], scope=None, language_code="en")

    # Запускаем слушатель очереди результатов
    asyncio.create_task(consume_results(bot))


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🔌 Shutdown: закрываем соединение с БД")
    await db._pool.close()


async def main():
    # 1) Инициализация PostgreSQL
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}" \
          f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Инициализация Aiogram: бот и диспетчер с Redis FSM
    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp  = Dispatcher(storage=RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    ))

    # 3) Middleware авторизации
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 4) Регистрируем роутеры **в этом порядке**:
    dp.include_router(start_router)
    dp.include_router(students_router)
    dp.include_router(ocrgen_router)   # ловит фото/документы и сразу запускает OCR+генерацию
    dp.include_router(gen_router)      # ручная генерация по тексту
    dp.include_router(chatgpt_router)
    dp.include_router(subscription_router)
    dp.include_router(settings_router)

    # 5) Запускаем polling
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )

if __name__ == "__main__":
    asyncio.run(main())