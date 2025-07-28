import asyncio
import logging
import json
import os
import base64
from io import BytesIO

import aio_pika
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from bot_app import config
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Параметры RabbitMQ из окружения
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

# Инициализация бота
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

async def process_result(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            data = json.loads(message.body.decode())
            logging.info(f"✅ Получен результат: {json.dumps(data, ensure_ascii=False)}")
        except Exception as e:
            logging.error(f"Invalid message format: {e}")
            return

        user_id = data.get("user_id")
        t = data.get("type")
        student_id = data.get("student_id")

        try:
            if t == "plan":
                text = f"📄 План:\n{data.get('plan_text', '(пусто)')}"
                await bot.send_message(user_id, text, reply_markup=result_plan_kb(student_id, lang="RU"))

            elif t == "tasks":
                text = f"📝 Задания:\n{data.get('tasks_text', '(нет)')}"
                await bot.send_message(user_id, text, reply_markup=result_tasks_kb(student_id, lang="RU"))

            elif t == "check":
                text = f"✔️ Проверка:\n{data.get('report_text', '(нет)')}"
                await bot.send_message(user_id, text, reply_markup=result_check_kb(student_id, lang="RU"))
                file_b64 = data.get("file")
                if file_b64:
                    file_bytes = base64.b64decode(file_b64)
                    file_obj = BytesIO(file_bytes)
                    file_obj.name = "Homework_Report.pdf"
                    await bot.send_document(user_id, file_obj, caption="📎 Отчёт в PDF")

            elif t == "chat":
                await bot.send_message(user_id, data.get("answer", ""), reply_markup=chat_gpt_back_kb(lang="RU"))

            elif t == "ocr":
                text = f"🖼️ Распознанный текст:\n{data.get('text', '(пусто)')}"
                await bot.send_message(user_id, text)

            elif t == "error":
                await bot.send_message(user_id, f"⚠️ {data.get('message', 'Error')}")

        except Exception as err:
            logging.error(f"❌ Ошибка при отправке сообщения в Telegram: {err}")

async def main():
    logging.info("🚀 Запуск queue-server. Подключаемся к RabbitMQ...")
    await asyncio.sleep(5)

    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASS,
        reconnect_interval=5,
    )
    logging.info("✅ Подключено к RabbitMQ")

    channel = await connection.channel()
    queue = await channel.declare_queue(RABBITMQ_RESULT_QUEUE, durable=True)
    await queue.consume(process_result)
    logging.info(f"🔔 Подписаны на очередь '{RABBITMQ_RESULT_QUEUE}'")

    # Ожидаем сообщений
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⛔ Остановка queue-server")
