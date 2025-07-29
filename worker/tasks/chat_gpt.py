import logging
from worker.services.gpt_service import chat_with_gpt
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
        prev_json = await redis_cache.get_conversation(user_id, student_id)
        history = []
        if prev_json:
            import json
            history = json.loads(prev_json)
        history.append({"role": "user", "content": prompt})

        answer = await chat_with_gpt(
            messages=history,
            temperature=0.7,
            max_tokens=1000
        )
        history.append({"role": "assistant", "content": answer})
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
            "message": f"GPT error: {e}"
        }

async def handle_end_chat(task: dict) -> None:
    """
    Очистка истории переписки.
    """
    user_id = task["user_id"]
    student_id = task["student_id"]
    await redis_cache.clear_conversation(user_id, student_id)