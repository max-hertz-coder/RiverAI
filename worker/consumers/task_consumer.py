# worker/task_consumer.py
import logging
from typing import Optional

from worker.services.ocr_service import handle_ocr, handle_ocr_and_generate
from worker.services.plan_service import handle_plan
from worker.services.tasks_service import handle_tasks
from worker.services.chat_service import handle_chat
from worker.services.homework_check_service import handle_homework_check
from common.redis_utils import clear_conversation, get_context_by_task_id

logger = logging.getLogger(__name__)


async def process_task_message(task: dict) -> Optional[dict]:
    """
    Единая точка маршрутизации входящих задач из очереди.
    Возвращаем словарь результата или None (если задача некорректна).
    """
    task_id = task.get("task_id")
    task_type = (task.get("type") or "").strip()

    logger.info("🔧 Начинаем обработку задачи: task_id=%s, type=%s", task_id, task_type)
    logger.debug("🔧 Полная задача: %r", task)

    if not task_id:
        logger.error("🔴 Task missing task_id")
        return {"type": "error", "message": "Отсутствует task_id."}

    try:
        # === OCR ===
        if task_type == "ocr":
            return await handle_ocr(task)

        # === OCR + Генерация ===
        if task_type == "ocr_and_generate":
            return await handle_ocr_and_generate(task)

        # === OCR + Проверка ДЗ ===
        if task_type == "ocr_and_check":
            logger.info("🔧 OCR для проверки ДЗ: task_id=%s", task_id)
            ocr_result = await handle_ocr(task)

            if ocr_result.get("type") == "error":
                logger.error("🔴 OCR ошибка: %r", ocr_result)
                return ocr_result

            check_task = {"task_id": task_id, "text": ocr_result.get("text", "")}
            logger.info("🔧 Отправляем на проверку ДЗ (len=%d)", len(check_task["text"]))
            return await handle_homework_check(check_task)

        # === Генерация плана (если используется) ===
        if task_type == "generate_plan":
            return await handle_plan(task)

        # === Генерация заданий/решений (батчем — для скорости) ===
        if task_type in {"generate_tasks", "generate_solutions"}:
            logger.info("🔧 handle_tasks: task_id=%s", task_id)
            result = await handle_tasks(task)
            return result

        # === Проверка ДЗ по тексту ===
        if task_type == "check_homework":
            return await handle_homework_check(task)

        # === Чат ===
        if task_type == "chat":
            try:
                return await handle_chat(task)
            except Exception as e:
                logger.exception("Ошибка в чате: %s", e)
                return {"type": "error", "task_id": task_id, "message": f"Ошибка в чате: {e}"}

        # === Завершение чата ===
        if task_type == "end_chat":
            ctx = await get_context_by_task_id(task_id)
            if ctx:
                user_id = ctx.get("user_id")
                student_id = ctx.get("student_id")
                if user_id is not None and student_id is not None:
                    await clear_conversation(user_id, student_id)
            return {"type": "chat", "task_id": task_id, "answer": "🗑️ Диалог очищен."}

        # === Неизвестный тип ===
        logger.warning("Unknown task type: %s", task_type)
        return {"type": "error", "task_id": task_id, "message": f"Неизвестный тип задачи: {task_type}"}

    except Exception as e:
        logger.exception("🔴 Error processing task type=%s task_id=%s: %s", task_type, task_id, e)
        return {"type": "error", "task_id": task_id, "message": "Внутренняя ошибка обработки задачи."}
