
# 📁 Новый файл: worker/services/

import logging
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

async def handle_chat(task: dict) -> dict:
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    messages = task.get("messages")

    if not messages or not isinstance(messages, list):
        return {
            "type": "error",
            "user_id": user_id,
            "message": "История сообщений пуста или в неверном формате."
        }

    try:
        answer = await chat_with_gpt(messages)
        return {
            "type": "chat",
            "user_id": user_id,
            "student_id": student_id,
            "answer": answer.strip()
        }
    except Exception as e:
        logger.exception("Ошибка в handle_chat")
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Ошибка при обработке сообщения GPT."
        }