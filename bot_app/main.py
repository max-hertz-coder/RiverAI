import asyncio
import logging
import json

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

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
    logging.info("Запуск бота и инициализация ресурсов...")
    # 1) Инициализируем пул PostgreSQL
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)

    # 2) Регистрируем команды для нижнего меню Telegram
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

    # 4) Декларируем очереди
    await rabbit_channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    result_queue = await rabbit_channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)

    # 5) Стартуем прослушку результатов
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))

async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("Останавливаем бота, закрываем пулы...")
    if db._pool:
        await db._pool.close()

async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    """Обработка сообщений из очереди результатов."""
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"Неверный формат сообщения: {e}")
            return
        user_id = data.get("user_id")
        result_type = data.get("type")
        # Route based on result type (same logic as before)
        if result_type == "plan":
            plan_text = data.get("plan_text") or "(пусто)"
            file_url = data.get("file_url")
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
                import base64
                from aiogram.types import BufferedInputFile
                pdf_bytes = base64.b64decode(file_base64)
                input_file = BufferedInputFile(pdf_bytes, filename="Tasks.pdf")
                await bot.send_document(user_id, input_file, caption="PDF с заданиями")
            elif file_url:
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
            await bot.send_message(
                user_id,
                data.get("answer",""),
                reply_markup=chat_gpt_back_kb(lang="RU")
            )

        elif result_type == "error":
            await bot.send_message(user_id, f"⚠️ {data.get('message','Произошла ошибка.')}")


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    ))

    # Подключаем middlewares
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Регистрируем роутеры
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