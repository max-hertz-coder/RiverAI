import logging

from worker.services.ocr_service       import ocr_openai_vision
from worker.services.generation_service import generate_raw_tasks, generate_raw_solutions
from worker.services.corrections_service import generate_corrected_tasks

async def process_task_message(task: dict) -> dict | None:
    """
    По полю task["type"] вызывает нужный сервис
    и возвращает словарь с полем "type" для очереди результатов.
    """
    t = task.get("type")
    user_id    = task.get("user_id")
    student_id = task.get("student_id")

    try:
        if t == "ocr":
            # Открываем файл по пути, переданному ботом
            path = task["file_path"]
            text = await ocr_openai_vision(path)
            return {
                "type": "ocr_result",
                "user_id": user_id,
                "student_id": student_id,
                "text": text,
            }

        if t == "generate_tasks":
            prompt = task.get("prompt", "")
            raw    = await generate_raw_tasks(prompt)
            return {
                "type": "generate_tasks_result",
                "user_id": user_id,
                "student_id": student_id,
                "raw_tasks": raw,
            }

        if t == "generate_solutions":
            raw_tasks = task.get("raw_tasks", "")
            sols      = await generate_raw_solutions(raw_tasks)
            return {
                "type": "generate_solutions_result",
                "user_id": user_id,
                "student_id": student_id,
                "solutions": sols,
            }

        if t == "correct_tasks":
            instr     = task.get("instruction", "")
            raw_tasks = task.get("raw_tasks", "")
            corrected = await generate_corrected_tasks(instr, raw_tasks)
            return {
                "type": "correct_tasks_result",
                "user_id": user_id,
                "student_id": student_id,
                "corrected": corrected,
            }

        logging.warning("Unknown task type: %s", t)

    except Exception:
        logging.exception("🔴 Error processing task %r", task)

    return None
