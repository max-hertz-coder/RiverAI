import uuid
import json
import logging
from typing import Dict, Any

from common.redis_utils import save_context, get_context_by_task_id, cleanup_task_context as cleanup_context

def generate_task_id() -> str:
    """Генерирует уникальный ID для задачи"""
    return str(uuid.uuid4())

async def create_task_with_context(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создает задачу с task_id и сохраняет контекст в Redis
    
    Args:
        task_data: Исходные данные задачи (должен содержать user_id и student_id)
    
    Returns:
        Обновленная задача с task_id, но без user_id и student_id
    """
    task_id = generate_task_id()
    
    # Извлекаем контекст пользователя
    user_id = task_data.pop("user_id", None)
    student_id = task_data.pop("student_id", None)
    
    if not user_id:
        raise ValueError("user_id обязателен для создания задачи")
    
    # Сохраняем контекст в Redis
    context = {
        "user_id": user_id,
        "student_id": student_id,
        "task_type": task_data.get("type")
    }
    
    print(f"🔧 Сохраняем контекст в Redis: task_id={task_id}, context={context}")
    await save_context(task_id, context)
    
    # Добавляем task_id к задаче
    task_data["task_id"] = task_id
    
    logging.info(f"📝 Создана задача task_id={task_id} для user_id={user_id}")
    
    return task_data

async def get_task_context(task_id: str) -> Dict[str, Any] | None:
    """Получает контекст задачи по task_id"""
    return await get_context_by_task_id(task_id)

async def cleanup_task_context(task_id: str) -> None:
    """Удаляет контекст задачи после обработки"""
    await cleanup_context(task_id) 