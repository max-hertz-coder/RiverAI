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
from bot_app.keyboards.main_menu import bottom_menu_kb  # ваша новая нижняя клавиатура
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
    logging.info("=== on_startup: инициализация ресурсов ===")

    # 1) Подключаемся к удалённой БД
    dsn = (
        f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )
    await db.init_db_pool(dsn)  # здесь _pool установится

    # 2) Настраиваем нижнее меню (кнопки под полем ввода)
    await bot.set_my_commands([
        BotCommand("show_students", "👤 Ученики"),
        BotCommand("add_student",   "➕ Добавить ученика"),
        BotCommand("settings",      "⚙️ Настройки"),
        BotCommand("subscription",  "💳 Оплата"),
    ])

    # 3) Поднимаем RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS
    )
    global rabbit_channel
    rabbit_channel = await connection.channel()

    # 4) Декларируем очереди
    await rabbit_channel.declare_queue(config.RABBITMQ_TASK_QUEUE, durable=True)
    result_queue = await rabbit_channel.declare_queue(config.RABBITMQ_RESULT_QUEUE, durable=True)

    # 5) Запускаем прослушку очереди
    await result_queue.consume(lambda msg: asyncio.create_task(process_result(msg, bot)))


async def on_shutdown(bot: Bot, dp: Dispatcher):
    logging.info("=== on_shutdown: закрываем пул БД ===")
    if db._pool:
        await db._pool.close()


async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body.decode())
        except Exception as e:
            logging.error(f"Неверный формат сообщения: {e}")
            return

        user_id = data.get("user_id")
        t       = data.get("type")

        if t == "plan":
            text = f"📄 План:\n{data.get('plan_text','(пусто)')}"
            await bot.send_message(user_id, text,
                reply_markup=result_plan_kb(data.get("student_id"), lang="RU"))

        elif t == "tasks":
            text = f"📝 Задания:\n{data.get('tasks_text','(нет данных)')}"
            await bot.send_message(user_id, text,
                reply_markup=result_tasks_kb(data.get("student_id"), lang="RU"))

        elif t == "check":
            text = f"✔️ Проверка:\n{data.get('report_text','(нет отчёта)')}"
            await bot.send_message(user_id, text,
                reply_markup=result_check_kb(data.get("student_id"), lang="RU"))

        elif t == "chat":
            await bot.send_message(user_id, data.get("answer",""),
                reply_markup=chat_gpt_back_kb(lang="RU"))

        elif t == "error":
            await bot.send_message(user_id, f"⚠️ {data.get('message','Ошибка')}")

async def main():
    logging.basicConfig(level=logging.INFO)

    # 1) Создаём бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 2) Диспетчер с FSM-хранилищем
    dp = Dispatcher(storage=RedisStorage.from_url(
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    ))

    # 3) Middlewares (AuthMiddleware вторит запросы к БД)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # 4) Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(students.router)
    dp.include_router(generation.router)
    dp.include_router(chatgpt.router)
    dp.include_router(subscription.router)
    dp.include_router(settings.router)

    # 5) Стартуем polling (on_startup и on_shutdown гарантированно выполнятся)
    await dp.start_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)


if __name__ == "__main__":
    asyncio.run(main())
