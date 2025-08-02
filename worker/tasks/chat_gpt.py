import logging
import json
from worker.services.chat_gpt_service import handle_chat_gpt
from worker import redis_cache

async def handle_chat_gpt(task: dict) -> dict:
    """
    Чат с GPT — с сохранением истории в Redis.
    """
    user_id = task["user_id"]
    student_id = task["student_id"]
    prompt = task.get("message", "").strip()

    if not prompt:
        return {
            "type": "error",
            "user_id": user_id,
            "message": "❌ Пустой запрос"
        }

    try:
        # Получаем историю из Redis
        prev_json = await redis_cache.get_conversation(user_id, student_id)
        history = []
        if prev_json:
            history = json.loads(prev_json)
        
        # Добавляем новое сообщение пользователя
        history.append({"role": "user", "content": prompt})

        # Используем новый сервис для чата с GPT
        result = await handle_chat_gpt({
            "task_id": f"{user_id}_{student_id}_{len(history)}",
            "message": prompt,
            "context": json.dumps(history[:-1], ensure_ascii=False) if len(history) > 1 else ""
        })
        
        if result.get("type") == "error":
            return {
                "type": "error",
                "user_id": user_id,
                "message": result.get("message", "Ошибка при обработке чата")
            }
        
        answer = result.get("gpt_response", "")
        
        # Добавляем ответ GPT в историю
        history.append({"role": "assistant", "content": answer})
        
        # Сохраняем обновленную историю в Redis
        await redis_cache.save_conversation(user_id, student_id, json.dumps(history, ensure_ascii=False))

        return {
            "type": "chat",
            "user_id": user_id,
            "student_id": student_id,
            "answer": answer
        }

    except Exception as e:
        logging.exception("Ошибка в chat_gpt")
        return {
            "type": "error",
            "user_id": user_id,
            "message": f"Ошибка при обработке чата: {e}"
        }

async def handle_end_chat(task: dict) -> None:
    """
    Очистка истории переписки.
    """
    user_id = task["user_id"]
    student_id = task["student_id"]
    await redis_cache.clear_conversation(user_id, student_id)