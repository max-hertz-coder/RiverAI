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
    chat_menu_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb,
)

rabbit_channel: aio_pika.Channel | None = None


async def process_result(message: aio_pika.IncomingMessage) -> None:
    """
    Обработка сообщений из очереди результатов.
    Рассылает их в Telegram.
    """
    async with message.process():
        try:
            data = json.loads(message.body)
        except Exception as e:
            logging.error(f"❌ process_result: неверный JSON: {e}")
            return

        user_id = data.get("user_id")
        t       = data.get("type")
        logging.info(f"✅ Получен результат для user={user_id}, type={t}")

        # берём ссылку на бот из атрибута функции
        bot: Bot = process_result.bot  

        if t == "plan":
            text = f"📄 План:\n{data.get('plan_text', '(пусто)')}"
            await bot.send_message(user_id, text,
                                   reply_markup=result_plan_kb(data.get("student_id")))
        elif t == "tasks":
            text = f"📝 Задания:\n{data.get('tasks_text', '(нет данных)')}"
            await bot.send_message(user_id, text,
                                   reply_markup=result_tasks_kb(data.get("student_id")))
        elif t == "check":
            text = f"✔️ Проверка:\n{data.get('report_text', '(нет отчёта)')}"
            await bot.send_message(user_id, text,
                                   reply_markup=result_check_kb(data.get("student_id")))
        elif t == "chat":
            await bot.send_message(user_id, data.get("answer", ""),
                                   reply_markup=chat_gpt_back_kb())
        elif t == "error":
            await bot.send_message(user_id, f"⚠️ {data.get('message')}")
        else:
            logging.warning(f"❓ Неизвестный тип результата: {t}")


async def on_startup(bot: Bot, dp: Dispatcher) -> None:
    logging.info("🚀 on_startup: инициализация БД, RabbitMQ и команд")

    # 1) Инициализируем пул PostgreSQL
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Пул PostgreSQL готов")

    # 2) Регистрируем команды в меню Telegram
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
    channel = await connection.channel()
    logging.info("✔️ Подключились к RabbitMQ")

    # 4) Объявляем очереди задач и результатов
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    result_q = await channel.declare_queue(config.RESULT_QUEUE, durable=True)
    logging.info(f"✔️ Очередь результатов готова: {config.RESULT_QUEUE}")

    # 5) Подписываемся на получение результатов
    process_result.bot = bot  # привязываем объект бота
    await result_q.consume(process_result, no_ack=False)
    logging.info("🔔 Подписались на очередь результатов")


async def on_shutdown(bot: Bot, dp: Dispatcher) -> None:
    logging.info("🔌 on_shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # 1) Создаём Telegram-бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    # 2) Конфигурируем диспетчер с Redis-хранилищем
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )
    # 3) Middlewares
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    # 4) Роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)
    # 5) Запускаем Polling с пропуском старых апдейтов
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )


if __name__ == "__main__":
    asyncio.run(main())
