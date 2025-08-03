
# 📁 Новый файл: worker/services/

import logging
from worker.services.gpt_service import chat_with_gpt
from common.redis_utils import get_context_by_task_id

logger = logging.getLogger(__name__)

async def handle_chat(task: dict) -> dict:
    task_id = task.get("task_id")
    message = task.get("message", "").strip()
    task_type = task.get("type")

    if not task_id:
        return {
            "type": "error",
            "message": "Отсутствует task_id."
        }

    try:
        # Получаем контекст из Redis
        context = await get_context_by_task_id(task_id)
        if not context:
            return {
                "type": "error",
                "message": "Контекст задачи не найден."
            }

        user_id = context.get("user_id")
        student_id = context.get("student_id")

        logger.info(f"🔧 Обрабатываем чат: task_id={task_id}, user_id={user_id}, student_id={student_id}")

        if task_type == "end_chat":
            # Очищаем историю диалога
            from common.redis_utils import clear_conversation
            await clear_conversation(user_id, student_id)
            return {
                "type": "chat",
                "answer": "🗑️ Диалог очищен."
            }

        # Получаем историю диалога
        from common.redis_utils import get_conversation, save_conversation
        history_json = await get_conversation(user_id, student_id)
        
        if history_json:
            import json
            messages = json.loads(history_json)
            logger.info(f"🔧 Найдена история диалога: {len(messages)} сообщений")
        else:
            messages = []
            logger.info(f"🔧 История диалога пуста, начинаем новый диалог")

        # Добавляем новое сообщение
        messages.append({"role": "user", "content": message})
        logger.info(f"🔧 Добавлено сообщение пользователя: {len(message)} символов")

        # Получаем ответ от GPT
        logger.info(f"🔧 Отправляем запрос к GPT...")
        answer = await chat_with_gpt(messages)
        logger.info(f"🔧 Получен ответ от GPT: {len(answer)} символов")
        
        # Добавляем ответ в историю
        messages.append({"role": "assistant", "content": answer})
        
        # Сохраняем обновленную историю
        await save_conversation(user_id, student_id, json.dumps(messages, ensure_ascii=False))
        logger.info(f"🔧 История диалога сохранена")

        return {
            "type": "chat",
            "answer": answer.strip()
        }
    except Exception as e:
        logger.exception(f"Ошибка в handle_chat: {e}")
        return {
            "type": "error",
            "message": "Ошибка при обработке сообщения GPT."
        }