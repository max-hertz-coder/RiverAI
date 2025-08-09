import uuid
import logging
from typing import Dict, Any, Optional

from common.redis_utils import save_context, get_context_by_task_id, cleanup_task_context as _cleanup_ctx


logger = logging.getLogger(__name__)


def generate_task_id() -> str:
    """Генерирует уникальный ID для задачи (UUID4)."""
    return str(uuid.uuid4())


async def create_task_with_context(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создаёт задачу с task_id и сохраняет контекст (user_id, student_id) в Redis.
    На выходе — копия task_data без персональных полей и с task_id.
    """
    task = dict(task_data)  # не мутируем входящий словарь
    task_id = generate_task_id()

    user_id: Optional[int] = task.pop("user_id", None)
    student_id: Optional[int] = task.pop("student_id", None)

    if not user_id:
        raise ValueError("user_id обязателен для создания задачи")

    context = {"user_id": user_id, "student_id": student_id, "task_type": task.get("type")}
    logger.debug("🔧 Сохраняем контекст: task_id=%s, context=%s", task_id, context)
    await save_context(task_id, context)

    task["task_id"] = task_id
    logger.info("📝 Создана задача task_id=%s для user_id=%s", task_id, user_id)
    return task


async def get_task_context(task_id: str) -> Dict[str, Any] | None:
    """Получает контекст задачи по task_id из Redis."""
    return await get_context_by_task_id(task_id)


async def cleanup_task_context(task_id: str) -> None:
    """Удаляет контекст задачи после обработки (успех/ошибка)."""
    await _cleanup_ctx(task_id)
