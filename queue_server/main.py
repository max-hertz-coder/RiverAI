import asyncio
import logging
import json

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
import asyncio
import logging
import json
import base64               # ← Добавить импорт
from io import BytesIO      # ← Добавить импорт

import aio_pika

from bot_app import config
from bot_app.database import db
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers import start, students, generation, chatgpt, subscription, settings
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    chat_menu_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb,
)

# Глобальный канал RabbitMQ
rabbit_channel: aio_pika.Channel = None

async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("=== on_startup: инициализация БД, Redis, RabbitMQ и меню команд ===")

    # 1) Инициализация пула PostgreSQL
    #   убедитесь, что в .env прописаны POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)  # теперь pool готов к работе :contentReference[oaicite:2]{index=2}

    # 2) Регистрируем команды нижнего меню (reply-кнопки)
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student",   "➕ Добавить ученика"),
        BotCommand("settings",      "⚙️ Настройки"),
        BotCommand("subscription",  "💳 Оплата"),
    ])

    # 3) Подключаемся к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    global rabbit_channel
    rabbit_channel = await connection.channel()

    # 4) Декларация очередей
    await rabbit_channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    result_queue = await rabbit_channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)

    # 5) Запуск прослушки результатов
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("=== on_shutdown: закрываем пул БД ===")
    if db._pool:
        await db._pool.close()



async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    """Обработка сообщений из очереди результатов."""
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"Invalid message format: {e}")
            return

        # Логируем полученный результат для отладки
        logging.info(f"Получен результат из очереди: {data}")  # ← Добавлено логирование

        user_id = data.get("user_id")
        t = data.get("type")

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
            # Если вместе с результатом есть PDF-файл (отчет), отправляем его пользователю
            file_b64 = data.get("file")
            if file_b64:
                file_bytes = base64.b64decode(file_b64)
                file_obj = BytesIO(file_bytes)
                file_obj.name = "Homework_Report.pdf"  # название файла для отправки
                await bot.send_document(user_id, file_obj, caption="📎 Отчёт в PDF")

        elif t == "chat":
            # Ответ на сообщение в GPT-чате
            await bot.send_message(user_id, data.get("answer", ""),
                                   reply_markup=chat_gpt_back_kb(lang="RU"))

        elif t == "ocr":
            # Отправляем распознанный текст (результат OCR)
            text = f"🖼️ Распознанный текст:\n{data.get('text', '(пусто)')}"
            await bot.send_message(user_id, text)

        elif t == "error":
            await bot.send_message(user_id, f"⚠️ {data.get('message', 'Error')}")
            
async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
        )
    )

    # Middlewares
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # Запускаем polling с on_startup и on_shutdown
    await dp.start_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)

if __name__ == "__main__":
    asyncio.run(main())
