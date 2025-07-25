import logging
from worker.services.ocr_service        import handle_ocr
from worker.services.plan_service       import handle_plan
from worker.services.tasks_service      import handle_tasks
from worker.services.check_service      import handle_check
from worker.services.chat_service       import handle_chat
from worker.services.chat_service import handle_chat
from worker.tasks.chat_gpt import handle_end_chat  # ← Добавить импорт


async def process_task_message(task: dict) -> dict | None:
    t = task.get("type")
    user_id    = task.get("user_id")
    student_id = task.get("student_id")

    try:
        if t == "ocr":
            return await handle_ocr(task)

        if t == "generate_plan":
            return await handle_plan(task)

        if t == "generate_tasks":
            return await handle_tasks(task)

        if t == "generate_solutions":
            # если у вас отдельно задачи и решения, можно вызвать handle_tasks/handle_solutions
            return await handle_tasks(task)

        if t == "check_homework":
            return await handle_check(task)

        if t == "chat_gpt":
            return await handle_chat(task)
        
        if t == "chat":
            return await handle_chat(task)
        if t == "end_chat":
        # Очистка истории диалога в Redis, результат не требуется
            await handle_end_chat(task)
            return None

        logging.warning("Unknown task type: %s", t)
    except Exception:
        logging.exception("🔴 Error processing task %r", task)

    return None
