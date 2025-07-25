import asyncio
import logging
import json
import base64
from io import BytesIO

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

# ✅ NEW: глобальный бот для всех
bot: Bot = None

async def process_result(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"Invalid message format: {e}")
            return

        logging.info(f"✅ Получен результат из result_queue: {data}")  # ✅ NEW

        user_id = data.get("user_id")
        t = data.get("type")

        try:
            if t == "plan":
                text = f"📄 План:\n{data.get('plan_text', '(пусто)')}"
                await bot.send_message(user_id, text,
                    reply_markup=result_plan_kb(data.get("student_id"), lang="RU"))

            elif t == "tasks":
                text = f"📝 Задания:\n{data.get('tasks_text', '(нет)')}"
                await bot.send_message(user_id, text,
                    reply_markup=result_tasks_kb(data.get("student_id"), lang="RU"))

            elif t == "check":
                text = f"✔️ Проверка:\n{data.get('report_text', '(нет)')}"
                await bot.send_message(user_id, text,
                    reply_markup=result_check_kb(data.get("student_id"), lang="RU"))
                file_b64 = data.get("file")
                if file_b64:
                    file_bytes = base64.b64decode(file_b64)
                    file_obj = BytesIO(file_bytes)
                    file_obj.name = "Homework_Report.pdf"
                    await bot.send_document(user_id, file_obj, caption="📎 Отчёт в PDF")

            elif t == "chat":
                await bot.send_message(user_id, data.get("answer", ""),
                    reply_markup=chat_gpt_back_kb(lang="RU"))

            elif t == "ocr":
                text = f"🖼️ Распознанный текст:\n{data.get('text', '(пусто)')}"
                await bot.send_message(user_id, text)

            elif t == "error":
                await bot.send_message(user_id, f"⚠️ {data.get('message', 'Error')}")
        except Exception as e:
            logging.error(f"❌ Ошибка при отправке сообщения в Telegram: {e}")


async def main():
    global bot
    logging.basicConfig(level=logging.INFO)

    # Создание Telegram-бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Создание диспетчера
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )

    # Middleware и роутеры
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # Инициализация БД
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)

    # Установка команд
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student", "➕ Добавить ученика"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("subscription", "💳 Оплата"),
    ])

    # Подключение к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()

    # Подписка на result_queue
    result_queue = await channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg)))  # ✅ NEW
    logging.info("🔔 Подписка на result_queue активирована")

    # Параллельный запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
