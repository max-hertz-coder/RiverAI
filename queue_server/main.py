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

import bot_app
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

# Глобальный канал RabbitMQ
rabbit_channel: aio_pika.Channel = None

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    """
    Обработка сообщений из очереди результатов и отправка в Telegram.
    """
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"Invalid message format: {e}")
            return

        logging.info(f"✅ Получен результат из очереди: {data}")
        user_id = data.get("user_id")
        t = data.get("type")
        student_id = data.get("student_id")

        try:
            if t == "plan":
                text = f"📄 План:\n{data.get('plan_text', '(пусто)')}"
                await bot.send_message(user_id, text,
                                       reply_markup=result_plan_kb(student_id, lang="RU"))

            elif t == "tasks":
                text = f"📝 Задания:\n{data.get('tasks_text', '(нет)')}"
                await bot.send_message(user_id, text,
                                       reply_markup=result_tasks_kb(student_id, lang="RU"))

            elif t == "check":
                text = f"✔️ Проверка:\n{data.get('report_text', '(нет)')}"
                await bot.send_message(user_id, text,
                                       reply_markup=result_check_kb(student_id, lang="RU"))
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

        except Exception as err:
            logging.error(f"❌ Ошибка при отправке сообщения в Telegram: {err}")


async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("=== on_startup: инициализация БД, Redis и RabbitMQ ===")

    # Инициализация PostgreSQL Pool
    dsn = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
        f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    await db.init_db_pool(dsn)

    # Регистрация команд
    await bot.set_my_commands([
        BotCommand(command="show_students", description="👤 Ученики"),
        BotCommand(command="add_student", description="➕ Добавить ученика"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="subscription", description="💳 Оплата"),
    ])

    # Подключение к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    global rabbit_channel
    rabbit_channel = await connection.channel()

    # Декларация очередей
    await rabbit_channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    result_queue = await rabbit_channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)

    # Запуск прослушки результатов
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))
    logging.info(f"🔔 Подписка на очередь '{config.RABBITMQ_RESULT_QUEUE}' активирована")


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("=== on_shutdown: закрываем пул БД ===")
    if db._pool:
        await db._pool.close()


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
    ))

    # Middlewares и роутеры
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    await on_startup(bot, dp)
    await dp.start_polling(bot, on_shutdown=on_shutdown)


if __name__ == "__main__":
    asyncio.run(main())
