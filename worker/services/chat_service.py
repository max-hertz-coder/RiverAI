
# 📁 Новый файл: worker/services/

import logging
from worker.services.gpt_service import chat_with_gpt
from common.redis_utils import get_context_by_task_id

logger = logging.getLogger(__name__)

async def handle_chat(task: dict) -> dict:
    task_id = task.get("task_id")
    message = task.get("message", "").strip()
    task_type = task.get("type")

    logger.info(f"🔧 Получена задача чата: task_id={task_id}, type={task_type}, message_length={len(message)}")

    if not task_id:
        return {
            "type": "error",
            "message": "Отсутствует task_id."
        }

    if not message and task_type != "end_chat":
        return {
            "type": "error",
            "message": "Сообщение пустое."
        }

    try:
        # Получаем контекст из Redis
        context = await get_context_by_task_id(task_id)
        if not context:
            logger.error(f"🔴 Контекст не найден для task_id={task_id}")
            return {
                "type": "error",
                "message": "Контекст задачи не найден."
            }

        logger.info(f"🔧 Контекст найден: {context}")

        user_id = context.get("user_id")
        student_id = context.get("student_id")

        logger.info(f"🔧 Обрабатываем чат: task_id={task_id}, user_id={user_id}, student_id={student_id}")

        # Проверяем, что user_id и student_id есть
        if not user_id:
            logger.error(f"🔴 user_id отсутствует в контексте")
            return {
                "type": "error",
                "message": "Ошибка: отсутствует user_id в контексте."
            }
        
        if not student_id:
            logger.error(f"🔴 student_id отсутствует в контексте")
            return {
                "type": "error",
                "message": "Ошибка: отсутствует student_id в контексте."
            }

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
            try:
                messages = json.loads(history_json)
                logger.info(f"🔧 Найдена история диалога: {len(messages)} сообщений")
            except json.JSONDecodeError as e:
                logger.error(f"🔴 Ошибка декодирования истории диалога: {e}")
                messages = []
        else:
            messages = []
            logger.info(f"🔧 История диалога пуста, начинаем новый диалог")

        # Добавляем новое сообщение
        messages.append({"role": "user", "content": message})
        logger.info(f"🔧 Добавлено сообщение пользователя: {len(message)} символов")

        # Проверяем сообщения перед отправкой к GPT
        logger.info(f"🔧 Проверяем сообщения для GPT:")
        for i, msg in enumerate(messages):
            logger.info(f"  [{i}] {msg['role']}: {msg['content'][:50]}...")

        # Получаем ответ от GPT
        logger.info(f"🔧 Отправляем запрос к GPT...")
        answer = await chat_with_gpt(messages)
        logger.info(f"🔧 Получен ответ от GPT: {len(answer)} символов")
        
        # Добавляем ответ в историю
        messages.append({"role": "assistant", "content": answer})
        
        # Сохраняем обновленную историю
        try:
            await save_conversation(user_id, student_id, json.dumps(messages, ensure_ascii=False))
            logger.info(f"🔧 История диалога сохранена")
        except Exception as e:
            logger.error(f"🔴 Ошибка сохранения истории диалога: {e}")
            # Продолжаем выполнение, даже если сохранение не удалось

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