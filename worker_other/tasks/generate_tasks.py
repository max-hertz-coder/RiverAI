### ✅ ОБНОВЛЕННЫЙ ФАЙЛ: worker/tasks/generate_tasks.py

import logging
from worker.services.tasks_service import handle_tasks

logger = logging.getLogger(__name__)

async def handle_generate_tasks(task: dict) -> None:
    task_id = task.get("task_id")
    logger.info(f"[WORKER] 🔧 handle_generate_tasks вызван: task_id={task_id}")
    await handle_tasks(task)