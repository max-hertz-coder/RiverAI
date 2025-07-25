from worker.services.generation_service import generate_raw_tasks

# worker/services/tasks_service.py

async def handle_tasks(task: dict) -> dict:
    """Генерация набора заданий по тексту prompt."""
    raw_tasks = await generate_raw_tasks(task["description"])
    return {
        "type": "tasks",               # было "generate_tasks_result"
        "user_id": task["user_id"],
        "student_id": task["student_id"],
        "tasks_text": raw_tasks        # было "raw_tasks"
    }
