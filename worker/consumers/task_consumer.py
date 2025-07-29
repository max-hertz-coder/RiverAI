import logging

from worker.services.ocr_service import sync_ocr
from worker.services.plan_service import handle_plan
from worker.services.tasks_service import handle_tasks
from worker.tasks.check_homework import handle_check_homework, handle_refine_check
from worker.tasks.chat_gpt import handle_chat_gpt, handle_end_chat

async def process_task_message(task: dict) -> dict | None:
    """
    Обрабатывает задачу из очереди task_queue и возвращает результат или None.
    """
    t = task.get("type")
    try:
        if t == "ocr":
            return await sync_ocr(task)

        if t == "generate_plan":
            return await handle_plan(task)

        if t == "generate_tasks":
            return await handle_tasks(task)

        if t in ("generate_solutions",):
            return await handle_tasks(task)

        if t == "check_homework":
            return await handle_check_homework(task)

        #if t == "refine_check":
        #    return await handle_refine_check(task)

        if t in ("chat_gpt", "chat"):
            return await handle_chat_gpt(task)

        if t == "end_chat":
            await handle_end_chat(task)
            return None

        logging.warning("Unknown task type: %s", t)
    except Exception:
        logging.exception("🔴 Error processing task %r", task)
    return None
