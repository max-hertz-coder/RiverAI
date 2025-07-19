import asyncio
import logging
import json

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
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb,
)

# RabbitMQ globals
rabbit_connection: aio_pika.RobustConnection | None = None
rabbit_channel: aio_pika.RobustChannel     | None = None


async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"❌ Invalid JSON in result: {e}")
            return

        user_id     = data.get("user_id")
        result_type = data.get("type")

        if result_type == "plan":
            text = f"📄 План:\n{data.get('plan_text','(пусто)')}"
            await bot.send_message(user_id, text, reply_markup=result_plan_kb(data.get("student_id"), lang="RU"))
        elif result_type == "tasks":
            text = f"📝 Задания:\n{data.get('tasks_text','(нет данных)')}"
            await bot.send_message(user_id, text, reply_markup=result_tasks_kb(data.get("student_id"), lang="RU"))
        elif result_type == "check":
            text = f"✔️ Результаты:\n{data.get('report_text','(нет отчёта)')}"
            await bot.send_message(user_id, text, reply_markup=result_check_kb(data.get("student_id"), lang="RU"))
        elif result_type == "chat":
            answer = data.get("answer","(нет ответа)")
            await bot.send_message(user_id, answer, reply_markup=chat_gpt_back_kb(lang="RU"))
        else:
            logging.warning(f"⚠️ Unknown result type: {result_type}")


async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("=== on_startup ===")
    # 2) set bot commands
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student",   "➕ Добавить ученика"),
        BotCommand("settings",      "⚙️ Настройки"),
        BotCommand("subscription",  "💳 Оплата"),
    ])

    # 3) connect to RabbitMQ
    global rabbit_connection, rabbit_channel
    rabbit_connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    rabbit_channel = await rabbit_connection.channel()
    logging.info("✔️ RabbitMQ connected")

    # 4) start consuming results
    result_queue = await rabbit_channel.declare_queue(config.RESULT_QUEUE, durable=True)
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))
    logging.info(f"✅ Started consumer for queue '{config.RESULT_QUEUE}'")


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("=== on_shutdown ===")
    if db._pool:
        await db._pool.close()
    if rabbit_connection:
        await rabbit_connection.close()



async def main():
    logging.basicConfig(level=logging.INFO)

    # 1) Инициализируем пул БД сразу, чтобы AuthMiddleware работал уже с ним
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Database pool initialized (pre-start)")

    # 2) Создаём Bot
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 3) Диспетчер с Redis-FSM
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )

    # 4) Middleware (AuthMiddleware потребует доступ к БД)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 5) Роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # 6) Запускаем polling
    await dp.start_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)

if __name__ == "__main__":
    asyncio.run(main())

