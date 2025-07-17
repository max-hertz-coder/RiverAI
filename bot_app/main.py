import asyncio
import logging
import json

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

import aio_pika
import asyncpg
import redis.asyncio as redis

from aiogram import Bot
from aiogram.client.session import DefaultBotProperties


from bot_app import config
from bot_app import database
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers import start, students, generation, chatgpt, subscription, settings
from bot_app.keyboards.chat_menu import chat_gpt_back_kb, chat_menu_kb, result_plan_kb, result_tasks_kb, result_check_kb

# Global RabbitMQ channel for publishing tasks (will be set in on_startup)
rabbit_channel: aio_pika.Channel = None

async def on_startup(bot: Bot, dp: Dispatcher):
    """Setup resources (DB, Redis, RabbitMQ) and background consumer on startup."""
    # Initialize database connection pool
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await database.db.init_db_pool(dsn)
    # Setup Redis for FSM storage is done via RedisStorage, but we may also use it for caching if needed.
    # Initialize RabbitMQ connection and channel
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    global rabbit_channel
    rabbit_channel = await connection.channel()  # obtain channel
    # Declare task and result queues
    await rabbit_channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    result_queue = await rabbit_channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)
    # Start consuming results in background
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))

async def on_shutdown(bot: Bot, dp: Dispatcher):
    # Optionally close DB pool and other resources
    if database.db._pool:
        await database.db._pool.close()

async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    """Process messages from the result queue (sent by workers)."""
    async with message.process():
        try:
            data = json.loads(message.body.decode('utf-8'))
        except Exception as e:
            logging.error(f"Invalid message format: {e}")
            return
        user_id = data.get("user_id")
        result_type = data.get("type")
        # Route based on result type
        if result_type == "plan":
            # Send the generated plan text
            plan_text = data.get("plan_text") or "(пусто)"
            file_url = data.get("file_url")  # could be 'yadisk' or actual URL or None
            # Compose message text
            text = f"📄 Сгенерированный учебный план:\n{plan_text}"
            if file_url == "yadisk":
                text += "\nФайл PDF сохранён на Яндекс.Диске."
            elif file_url and file_url.startswith("http"):
                text += "\nPDF: " + file_url
            await bot.send_message(user_id, text, reply_markup=result_plan_kb(data.get("student_id"), lang="RU"))
        elif result_type == "tasks":
            tasks_text = data.get("tasks_text") or "(нет данных)"
            file_url = data.get("file_url")
            file_base64 = data.get("file")
            text = f"📝 Сгенерированные задания:\n{tasks_text}"
            if file_url == "yadisk":
                text += "\nPDF сохранён на Я.Диске."
            elif file_base64:
                # If worker returned file content (base64), send as document
                import base64
                from aiogram.types import FSInputFile, BufferedInputFile
                pdf_bytes = base64.b64decode(file_base64)
                input_file = BufferedInputFile(pdf_bytes, filename="Tasks.pdf")
                await bot.send_document(user_id, input_file, caption="PDF с заданиями")
            elif file_url:
                # If provided a public URL (e.g., from S3), instruct Telegram to fetch and send
                await bot.send_document(user_id, file_url, caption="PDF с заданиями")
            await bot.send_message(user_id, "Выберите дальнейшие действия:", reply_markup=result_tasks_kb(data.get("student_id"), lang="RU"))
        elif result_type == "check":
            report_text = data.get("report_text") or "(нет отчёта)"
            file_url = data.get("file_url")
            file_base64 = data.get("file")
            text = f"✔️ Результаты проверки:\n{report_text}"
            if file_url == "yadisk":
                text += "\nОтчёт сохранён на Я.Диске."
            elif file_base64:
                import base64
                from aiogram.types import BufferedInputFile
                pdf_bytes = base64.b64decode(file_base64)
                input_file = BufferedInputFile(pdf_bytes, filename="HomeworkReport.pdf")
                await bot.send_document(user_id, input_file, caption="Отчёт проверки")
            elif file_url:
                await bot.send_document(user_id, file_url, caption="Отчёт проверки")
            await bot.send_message(user_id, "Выберите дальнейшие действия:", reply_markup=result_check_kb(data.get("student_id"), lang="RU"))
        elif result_type == "chat":
            answer = data.get("answer") or ""
            # Send the assistant's answer in chat context with a Back button
            await bot.send_message(user_id, answer, reply_markup=chat_gpt_back_kb(lang="RU"))
        elif result_type == "error":
            error_msg = data.get("message", "Произошла ошибка.")
            await bot.send_message(user_id, f"⚠️ {error_msg}")
        # else: ignore unknown types

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher(storage=RedisStorage.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"))
    # Register middlewares
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    # Register handlers from modules
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)
    # Start polling
    dp.run_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)
