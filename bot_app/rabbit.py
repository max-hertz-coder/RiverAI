### ✅ ОБНОВЛЕННЫЙ ФАЙЛ: bot_app/rabbit.py

import json
import logging
from io import BytesIO
import base64
from aiogram import Bot
from bot_app.redis_cache import get_context_by_task_id, delete_context_by_task_id
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb
)

pending_tasks: dict[tuple[int, int], str] = {}

async def process_result(message, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body)
            logging.info(f"📥 Результат из очереди: {data}")
        except Exception as e:
            logging.error(f"❌ Не удалось разобрать JSON: {e}")
            return

        task_id = data.get("task_id")
        if not task_id:
            logging.warning("⚠️ В результате нет task_id")
            return

        context = await get_context_by_task_id(task_id)
        if not context:
            logging.warning(f"⚠️ Контекст не найден для task_id={task_id}")
            return

        user_id = context.get("user_id")
        student_id = context.get("student_id")
        t = data.get("type")

        if not user_id or not t:
            logging.warning("⚠️ В результате нет user_id или type")
            return

        # — Tasks —
        if t == "tasks":
            raw = data.get("tasks_text", "").strip()
            pending_tasks[(user_id, student_id)] = raw

            await bot.send_message(
                user_id,
                f"📝 Задания:\n{raw}",
                reply_markup=result_tasks_kb(student_id)
            )

            file_tasks_b64 = data.get("file_tasks")
            file_solutions_b64 = data.get("file_solutions")

            if file_tasks_b64:
                file_bytes = base64.b64decode(file_tasks_b64)
                file_obj = BytesIO(file_bytes)
                file_obj.name = "Tasks.pdf"
                await bot.send_document(user_id, file_obj, caption="📎 PDF: Задания")

            if file_solutions_b64:
                file_bytes = base64.b64decode(file_solutions_b64)
                file_obj = BytesIO(file_bytes)
                file_obj.name = "Solutions.pdf"
                await bot.send_document(user_id, file_obj, caption="📎 PDF: Решения")

            logging.info(f"✅ Отправлено пользователю {user_id} по task_id={task_id}")

        await delete_context_by_task_id(task_id)
