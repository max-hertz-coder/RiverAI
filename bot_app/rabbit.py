import json
import logging
from aio_pika import IncomingMessage
from aiogram import Bot
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb, result_plan_kb, result_tasks_kb, result_check_kb
)

async def process_result(message: IncomingMessage, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body)
            logging.info(f"📥 Получен результат из очереди: {data}")
        except Exception as e:
            logging.error(f"❌ Ошибка при разборе JSON результата: {e}")
            return

        user_id = data.get("user_id")
        t       = data.get("type")
        student_id = data.get("student_id")

        if not user_id or not t:
            logging.warning("⚠️ Результат не содержит user_id или type")
            return

        if t == "chat":
            await bot.send_message(user_id, data.get("answer", "(нет ответа)"), reply_markup=chat_gpt_back_kb())
        elif t == "plan":
            await bot.send_message(user_id, f"📄 План:\n{data.get('plan_text', '(пусто)')}", reply_markup=result_plan_kb(student_id))
        elif t == "tasks":
            await bot.send_message(user_id, f"📝 Задания:\n{data.get('tasks_text', '(нет данных)')}", reply_markup=result_tasks_kb(student_id))
        elif t == "check":
            await bot.send_message(user_id, f"✔️ Результаты проверки:\n{data.get('report_text', '(нет отчёта)')}", reply_markup=result_check_kb(student_id))
        elif t == "error":
            await bot.send_message(user_id, f"⚠️ Ошибка: {data.get('message', 'Неизвестная ошибка')}")
        else:
            logging.warning(f"❓ Неизвестный тип результата: {t}")
