import logging
from worker.services.homework_check_service import handle_homework_check
from worker.services.result_publisher import publish_result

logger = logging.getLogger(__name__)


async def handle_check_homework(task: dict) -> None:
    """
    Обработчик задачи «check_homework».
    Генерирует payload и публикует его в RESULT_QUEUE.
    """
    try:
        result = await handle_homework_check(task)
        await publish_result(result)
    except Exception:
        logger.exception("🔴 Ошибка в handle_check_homework")
        try:
            await publish_result({
                "type": "error",
                "task_id": task.get("task_id"),
                "message": "Ошибка при проверке ДЗ на воркере."
            })
        except Exception:
            logger.exception("Не удалось опубликовать ошибку check_homework")
