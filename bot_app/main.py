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


async def process_result(message: aio_pika.IncomingMessage) -> None:
    """Обрабатываем каждое сообщение из очереди результатов и шлём его в Telegram."""
    async with message.process():
        try:
            data = json.loads(message.body)
        except Exception as e:
            logging.error(f"❌ process_result — неверный JSON: {e}")
            return

        user_id = data.get("user_id")
        t       = data.get("type")
        answer  = data.get("answer") or ""
        logging.info(f"▶ process_result: type={t} user={user_id}")

        if t == "chat":
            # вот здесь точно отправляем сообщение в чат
            await process_result.bot.send_message(
                user_id,
                answer,
                reply_markup=chat_gpt_back_kb()
            )
        elif t == "plan":
            text = f"📄 План:\n{data.get('plan_text','(пусто)')}"
            await process_result.bot.send_message(user_id, text, reply_markup=result_plan_kb(data.get("student_id")))
        elif t == "tasks":
            text = f"📝 Задания:\n{data.get('tasks_text','(нет данных)')}"
            await process_result.bot.send_message(user_id, text, reply_markup=result_tasks_kb(data.get("student_id")))
        elif t == "check":
            text = f"✔️ Результаты проверки:\n{data.get('report_text','(нет отчёта)')}"
            await process_result.bot.send_message(user_id, text, reply_markup=result_check_kb(data.get("student_id")))
        elif t == "error":
            await process_result.bot.send_message(user_id, f"⚠️ {data.get('message','Ошибка')}")
        else:
            logging.warning(f"❓ process_result: неизвестный type={t}")


async def on_startup(bot: Bot, dp: Dispatcher) -> None:
    logging.info("🚀 on_startup: регистрируем команды и подписываемся на очередь результатов")

    # 1) команды Telegram
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student",   "➕ Добавить ученика"),
        BotCommand("settings",      "⚙️ Настройки"),
        BotCommand("subscription",  "💳 Оплата"),
    ])

    # 2) подключаемся к RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    channel = await connection.channel()
    logging.info("✔️ Connected to RabbitMQ")

    # 3) декларируем очередь результатов и подписываемся
    result_q = await channel.declare_queue(config.RESULT_QUEUE, durable=True)
    process_result.bot = bot   # привязываем bot к обработчику
    await result_q.consume(process_result, no_ack=False)
    logging.info(f"🔔 Subscribed to result queue '{config.RESULT_QUEUE}'")


async def on_shutdown(bot: Bot, dp: Dispatcher) -> None:
    logging.info("🔌 on_shutdown: закрываем пул БД")
    if db._pool:
        await db._pool.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # 0) Инициализируем пул PostgreSQL ДО создания Dispatcher
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)
    logging.info("✔️ Database pool initialized")

    # 1) создаём бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 2) диспетчер с FSM на Redis
    dp = Dispatcher(
        storage=RedisStorage.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB_FSM}"
        )
    )

    # 3) middleware (AuthMiddleware сразу найдёт инициализированный пул)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 4) регистрируем все ваши роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # 5) стартуем polling
    await dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )


if __name__ == "__main__":
    asyncio.run(main())
