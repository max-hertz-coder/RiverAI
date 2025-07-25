#!/usr/bin/env python3
import asyncio
import logging
import json

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from bot_app import config, rabbit
from bot_app.database import db
from bot_app.middlewares.auth import AuthMiddleware
from bot_app.handlers import start, students, generation, chatgpt, subscription, settings
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb,
)


async def process_result(message, bot: Bot):
    """Обрабатывает результат из очереди и отправляет пользователю"""
    async with message.process():
        try:
            data = json.loads(message.body)
        except Exception as e:
            logging.error(f"❌ Ошибка парсинга JSON из result_queue: {e}")
            return

        user_id = data.get("user_id")
        t       = data.get("type")
        student_id = data.get("student_id")
        logging.info(f"📬 Получен результат type={t} для user_id={user_id}")

        if t == "chat":
            await bot.send_message(user_id, data.get("answer", "⚠️ Нет ответа"), reply_markup=chat_gpt_back_kb())
        elif t == "plan":
            await bot.send_message(user_id, f"📄 План:\n{data.get('plan_text', '(пусто)')}",
                                   reply_markup=result_plan_kb(student_id))
        elif t == "tasks":
            await bot.send_message(user_id, f"📝 Задания:\n{data.get('tasks_text', '(пусто)')}",
                                   reply_markup=result_tasks_kb(student_id))
        elif t == "check":
            await bot.send_message(user_id, f"✅ Проверка:\n{data.get('report_text', '(нет отчета)')}",
                                   reply_markup=result_check_kb(student_id))
        elif t == "error":
            await bot.send_message(user_id, f"❗ Ошибка: {data.get('message', 'неизвестная')}")
        else:
            logging.warning(f"❓ Неизвестный тип результата: {t}")


async def on_startup(bot: Bot, dp: Dispatcher):
    logging.info("🚀 on_startup: подключение к RabbitMQ и подписка на result_queue")

    # 1) Telegram-команды
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student", "➕ Добавить ученика"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("subscription", "💳 Подписка"),
    ])

    # 2) Подключение к RabbitMQ
    await rabbit.connect()
    await rabbit.declare_queues()

    # 3) Подписка на очередь результатов
    await rabbit.subscribe_result_queue(lambda msg: asyncio.create_task(process_result(msg, bot)))
    logging.info("📥 Подписка на очередь результатов завершена")


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🔌 Завершение работы: закрываем соединения")
    if db._pool:
        await db._pool.close()
    await rabbit.disconnect()


async def main():
    logging.basicConfig(level=logging.INFO)

    # 0) Инициализация базы данных
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)
    logging.info("✅ PostgreSQL подключен")

    # 1) Создание бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 2) Диспетчер + Redis
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )

    # 3) Middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 4) Роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # 5) Старт polling
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )


if __name__ == "__main__":
    asyncio.run(main())
