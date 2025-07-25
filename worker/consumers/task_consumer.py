# worker/consumers/task_consumer.py

import logging

from worker.services.ocr_service       import handle_ocr
from worker.services.plan_service      import handle_plan
from worker.services.tasks_service     import handle_tasks
from worker.services.solutions_service import handle_solutions
from worker.services.check_service     import handle_check
from worker.services.corrections_service import handle_corrections
from worker.services.chat_service      import handle_chat


async def process_task_message(task: dict) -> dict | None:
    """
    Dispatch incoming task by type to the appropriate service handler.
    Each handler must return a dict that includes at least:
      - "type":      the response type for the result queue (e.g. "ocr_result")
      - "user_id":   telegram user id
      - "student_id":student id context
      - other keys depending on the task
    """
    t = task.get("type")
    user_id    = task.get("user_id")
    student_id = task.get("student_id")

    try:
        if t == "ocr":
            # Распознать текст из изображения/PDF
            result = await handle_ocr(task)

        elif t == "generate_plan":
            # Сгенерировать учебный план
            result = await handle_plan(task)

        elif t == "generate_tasks":
            # Сгенерировать задания
            result = await handle_tasks(task)

        elif t == "generate_solutions":
            # Сгенерировать решения к заданиям
            result = await handle_solutions(task)

        elif t == "check_homework":
            # Проверить домашнюю работу
            result = await handle_check(task)

        elif t == "correct_tasks":
            # Отредактировать (скорректировать) готовые задания
            result = await handle_corrections(task)

        elif t == "chat_gpt":
            # Общение в контексте чата (ChatGPT)
            result = await handle_chat(task)

        else:
            logging.warning("Unknown task type: %s", t)
            return None

        # Всегда пробрасываем в результат идентификаторы user_id и student_id
        if isinstance(result, dict):
            result.setdefault("user_id", user_id)
            result.setdefault("student_id", student_id)
        return result

    except Exception:
        logging.exception("🔴 Error processing task %r", task)
        return None
