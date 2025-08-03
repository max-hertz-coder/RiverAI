
# 📁 Новый файл: worker/services/

import logging
from worker.services.gpt_service import chat_with_gpt
from common.redis_utils import get_context_by_task_id

logger = logging.getLogger(__name__)

async def handle_chat(task: dict) -> dict:
    logger.info(f"🔧 handle_chat: начало функции")
    
    try:
        task_id = task.get("task_id")
        message = task.get("message", "").strip()
        task_type = task.get("type")

        logger.info(f"🔧 handle_chat: task_id={task_id}, type={task_type}, message_length={len(message)}")

        if not task_id:
            logger.error("🔴 handle_chat: отсутствует task_id")
            return {
                "type": "error",
                "message": "Отсутствует task_id."
            }

        if not message and task_type != "end_chat":
            logger.error("🔴 handle_chat: сообщение пустое")
            return {
                "type": "error",
                "message": "Сообщение пустое."
            }

        # Получаем контекст из Redis
        logger.info(f"🔧 handle_chat: получаем контекст из Redis")
        context = await get_context_by_task_id(task_id)
        if not context:
            logger.error(f"🔴 handle_chat: контекст не найден для task_id={task_id}")
            return {
                "type": "error",
                "message": "Контекст задачи не найден."
            }

        logger.info(f"🔧 handle_chat: контекст найден")

        user_id = context.get("user_id")
        student_id = context.get("student_id")

        logger.info(f"🔧 handle_chat: user_id={user_id}, student_id={student_id}")

        # Проверяем, что user_id и student_id есть
        if not user_id:
            logger.error(f"🔴 handle_chat: user_id отсутствует в контексте")
            return {
                "type": "error",
                "message": "Ошибка: отсутствует user_id в контексте."
            }
        
        if not student_id:
            logger.error(f"🔴 handle_chat: student_id отсутствует в контексте")
            return {
                "type": "error",
                "message": "Ошибка: отсутствует student_id в контексте."
            }

        if task_type == "end_chat":
            logger.info(f"🔧 handle_chat: очищаем историю диалога")
            from common.redis_utils import clear_conversation
            await clear_conversation(user_id, student_id)
            return {
                "type": "chat",
                "answer": "🗑️ Диалог очищен."
            }

        # Простой ответ без GPT для тестирования
        logger.info(f"🔧 handle_chat: отправляем простой ответ")
        result = {
            "type": "chat",
            "answer": f"Тестовый ответ на сообщение: '{message}'. Worker работает!"
        }
        logger.info(f"🔧 handle_chat: результат = {result}")
        return result

    except Exception as e:
        logger.exception(f"🔴 handle_chat: неожиданная ошибка: {e}")
        return {
            "type": "error",
            "message": "Ошибка при обработке сообщения GPT."
        }