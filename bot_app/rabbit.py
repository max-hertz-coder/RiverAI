import json
import logging
from io import BytesIO
import base64

from aio_pika import IncomingMessage
from aiogram import Bot
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb
)

# В памяти храним последние raw-тексты задач для каждого (user_id, student_id)
pending_tasks: dict[tuple[int, int], str] = {}

async def process_result(message: IncomingMessage, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body)
            logging.info(f"📥 Получен результат из очереди: {data}")
        except Exception as e:
            logging.error(f"❌ Ошибка при разборе JSON результата: {e}")
            return

        user_id    = data.get("user_id")
        t          = data.get("type")
        student_id = data.get("student_id")

        if not user_id or not t:
            logging.warning("⚠️ Результат не содержит user_id или type")
            return

        # === Chat ===
        if t == "chat":
            await bot.send_message(
                user_id,
                data.get("answer", "(нет ответа)"),
                reply_markup=chat_gpt_back_kb()
            )

        # === Plan ===
        elif t == "plan":
            await bot.send_message(
                user_id,
                f"📄 План:\n{data.get('plan_text', '(пусто)')}",
                reply_markup=result_plan_kb(student_id)
            )

        # === Tasks ===
        elif t == "tasks":
            # Сохраняем в памяти raw-текст заданий
            raw = data.get("tasks_text", "").strip()
            pending_tasks[(user_id, student_id)] = raw

            # Отправляем текст и клавиатуру
            await bot.send_message(
                user_id,
                f"📝 Задания:\n{raw}",
                reply_markup=result_tasks_kb(student_id)
            )

        # === Homework Check ===
        elif t == "check":
            await bot.send_message(
                user_id,
                f"✔️ Результаты проверки:\n{data.get('report_text', '(нет отчёта)')}",
                reply_markup=result_check_kb(student_id)
            )
            file_b64 = data.get("file")
            if file_b64:
                file_bytes = base64.b64decode(file_b64)
                file_obj = BytesIO(file_bytes)
                file_obj.name = "Homework_Report.pdf"
                await bot.send_document(
                    user_id,
                    file_obj,
                    caption="📎 Отчёт в PDF"
                )

        # === OCR only ===
        elif t == "ocr":
            await bot.send_message(
                user_id,
                f"🖼️ Распознанный текст:\n{data.get('text', '(пусто)')}"
            )

        # === Error ===
        elif t == "error":
            await bot.send_message(
                user_id,
                f"⚠️ Ошибка: {data.get('message', 'Неизвестная ошибка')}"
            )

        else:
            logging.warning(f"❓ Неизвестный тип результата: {t}")