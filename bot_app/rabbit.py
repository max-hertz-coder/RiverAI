import json
import logging
import aio_pika
from aiogram import Bot
from aiogram.types import InputFile
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

async def process_result(message: aio_pika.IncomingMessage, bot: Bot):
    async with message.process():
        try:
            body = message.body.decode()
            data = json.loads(body)
        except Exception as e:
            logger.exception(f"📛 Ошибка декодирования сообщения из очереди: {e}")
            return

        user_id    = data.get("user_id")
        student_id = data.get("student_id")
        result_type = data.get("type")

        logger.info(f"📩 Получен результат '{result_type}' для user_id={user_id}")

        try:
            if result_type == "generate_plan_result":
                await bot.send_message(user_id, f"📋 Учебный план:\n{data.get('text')}")

            elif result_type == "chat_result":
                await bot.send_message(user_id, data.get("text", "🤖"))

            elif result_type == "ocr_result":
                await bot.send_message(user_id, f"🔍 Распознанный текст:\n{data.get('text')}")

            elif result_type == "generate_tasks_result":
                await bot.send_message(user_id, f"📝 Сырые задания:\n{data.get('raw_tasks')}")

            elif result_type == "generate_solutions_result":
                await bot.send_message(user_id, f"✅ Решения:\n{data.get('solutions')}")

            elif result_type == "correct_tasks_result":
                await bot.send_message(user_id, f"🧪 Скорректированные задания:\n{data.get('corrected')}")

            elif result_type == "check_homework_result":
                file_data = data.get("file_data")
                file_name = data.get("file_name", "check_result.pdf")
                if file_data:
                    decoded = base64.b64decode(file_data)
                    f = BytesIO(decoded)
                    f.name = file_name
                    await bot.send_document(user_id, InputFile(f))
                else:
                    await bot.send_message(user_id, "⚠️ Не удалось получить файл проверки")

            elif result_type == "error":
                await bot.send_message(user_id, f"❌ Ошибка:\n{data.get('message','Неизвестная ошибка')}")

            else:
                logger.warning(f"⚠️ Неизвестный тип результата: {result_type}")
                await bot.send_message(user_id, "⚠️ Получен неизвестный результат")

        except Exception as e:
            logger.exception(f"Ошибка при отправке результата пользователю {user_id}: {e}")
