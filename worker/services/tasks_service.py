# 📁 Новый файл: worker/services/tasks_service.py

from worker.services.generation_service import generate_raw_tasks, generate_raw_solutions
import logging

logger = logging.getLogger(__name__)

async def handle_tasks(task: dict) -> dict:
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    prompt = task.get("prompt", "").strip()

    if not prompt:
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Запрос для генерации заданий пуст."
        }

    try:
        if task["type"] == "generate_tasks":
            result_text = await generate_raw_tasks(prompt)
            return {
                "type": "tasks",
                "user_id": user_id,
                "student_id": student_id,
                "tasks_text": result_text.strip()
            }

        elif task["type"] == "generate_solutions":
            result_text = await generate_raw_solutions(prompt)
            return {
                "type": "tasks",
                "user_id": user_id,
                "student_id": student_id,
                "tasks_text": result_text.strip()
            }

        else:
            return {
                "type": "error",
                "user_id": user_id,
                "message": f"Неподдерживаемый тип задачи: {task['type']}"
            }
    except Exception as e:
        logger.exception("Ошибка при генерации задач или решений")
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Ошибка при генерации задания."
        }


