from worker.services.generation_service import generate_raw_tasks

async def handle_tasks(task: dict) -> dict:
    """
    Генерация набора заданий по тексту prompt.
    """
    raw = await generate_raw_tasks(task["description"])
    return {
        "type": "generate_tasks_result",
        "user_id": task["user_id"],
        "student_id": task["student_id"],
        "raw_tasks": raw
    }
