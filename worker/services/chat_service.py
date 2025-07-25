import logging
from worker.services.gpt_service import ask_gpt
from worker.redis_cache import get_conversation, save_conversation
import json

async def handle_chat(task: dict) -> dict:
    """
    Диалог с GPT: достаём историю из Redis, добавляем новое сообщение,
    отправляем в GPT, сохраняем ответ в истории и возвращаем ответ.
    """
    user_id    = task["user_id"]
    student_id = task["student_id"]
    msg        = task["message"]

    # получаем историю (json-строку) или начинаем новую
    hist_json = await get_conversation(user_id, student_id)
    history   = [] if not hist_json else json.loads(hist_json)

    answer = await ask_gpt(history)
    logging.info(f"[chat_service] Answer to queue: {answer}")

    # append user request
    history.append({"role": "user", "content": msg})
    answer = await ask_gpt(history)
    history.append({"role": "assistant", "content": answer})

    # сохраняем обновлённую историю
    await save_conversation(user_id, student_id, json.dumps(history))

    return {
        "type": "chat",
        "user_id": user_id,
        "student_id": student_id,
        "answer": answer
    }
