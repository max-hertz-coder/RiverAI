import logging

from worker.services.ocr_service import handle_ocr, handle_ocr_and_generate
from worker.services.plan_service import handle_plan
from worker.services.tasks_service import handle_tasks
from worker.tasks.check_homework import handle_check_homework
from worker.services.chat_service import handle_chat
from worker import redis_cache

async def process_task_message(task: dict) -> dict | None:
    """
    Обрабатывает задачу из очереди task_queue и возвращает результат или None.
    """
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    task_type = task.get("type")

    try:
        if task_type == "ocr_and_generate":
            return await handle_ocr_and_generate(task)

        if task_type == "ocr":
            return await handle_ocr(task)

        if task_type == "generate_plan":
            return await handle_plan(task)

        if task_type in ("generate_tasks", "generate_solutions"):
            return await handle_tasks(task)

        if task_type == "check_homework":
            return await handle_check_homework(task)

        if task_type in ("chat_gpt", "chat"):
            return await handle_chat(task)

        if task_type == "end_chat":
            # Очищаем историю диалога
            await redis_cache.clear_conversation(user_id, student_id)
            return {
                "type": "chat",
                "user_id": user_id,
                "student_id": student_id,
                "answer": "🗑️ Диалог очищен."
            }

        logging.warning("Unknown task type: %s", task_type)

    except Exception:
        logging.exception("🔴 Error processing task %r", task)
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Внутренняя ошибка обработки задачи."
        }

    return None