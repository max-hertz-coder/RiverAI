import logging
from worker.services.tasks_service import handle_tasks
from worker.services.result_publisher import publish_result

logger = logging.getLogger(__name__)

async def handle_generate_tasks(task: dict) -> None:
    """
    Обработчик задачи «generate_tasks»/«generate_solutions».
    Генерирует payload и публикует его в RESULT_QUEUE.
    """
    task_id = task.get("task_id")
    logger.info("[WORKER] 🔧 handle_generate_tasks: task_id=%s type=%s", task_id, task.get("type"))
    try:
        result = await handle_tasks(task)
        if result.get("type") == "error":
            logger.error("🔴 generate_tasks error: %s", result.get("message"))
        await publish_result(result)
    except Exception:
        logger.exception("🔴 Ошибка в handle_generate_tasks")
        try:
            await publish_result({
                "type": "error",
                "task_id": task_id,
                "message": "Ошибка генерации заданий на воркере."
            })
        except Exception:
            logger.exception("Не удалось опубликовать ошибку generate_tasks")
