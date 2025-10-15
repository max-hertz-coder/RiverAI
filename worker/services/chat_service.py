import json
import logging
from typing import List, Dict, Any

from worker.services.gpt_service import chat_with_gpt
from common.redis_utils import get_context_by_task_id, get_conversation, save_conversation, clear_conversation

logger = logging.getLogger(__name__)

async def _load_history(user_id: int, student_id: int | None) -> List[Dict[str, str]]:
    try:
        raw = await get_conversation(user_id, student_id or 0)
        return json.loads(raw) if raw else []
    except Exception:
        logger.exception("Ошибка чтения истории чата (user=%s, student=%s)", user_id, student_id)
        return []

async def _save_history(user_id: int, student_id: int | None, history: List[Dict[str, str]]) -> None:
    try:
        await save_conversation(user_id, student_id or 0, json.dumps(history, ensure_ascii=False))
    except Exception:
        logger.exception("Ошибка сохранения истории чата (user=%s, student=%s)", user_id, student_id)

async def handle_chat(task: dict) -> dict:
    """
    Унифицированный чат:
      - type: 'chat' — обычное сообщение
      - type: 'end_chat' — очистка истории
    """
    task_id = task.get("task_id")
    message = (task.get("message") or "").strip()
    task_type = (task.get("type") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Нет task_id"}
    if task_type != "end_chat" and not message:
        return {"type": "error", "task_id": task_id, "message": "Пустое сообщение"}

    ctx = await get_context_by_task_id(task_id)
    if not ctx:
        return {"type": "error", "task_id": task_id, "message": "Контекст не найден"}

    user_id = ctx.get("user_id")
    student_id = ctx.get("student_id")

    if task_type == "end_chat":
        await clear_conversation(user_id, student_id or 0)
        return {"type": "chat", "task_id": task_id, "answer": "🗑️ Диалог очищен."}

    # Загружаем историю диалога (контекст предыдущих сообщений)
    history = await _load_history(user_id, student_id)
    messages: List[Dict[str, str]] = history + [{"role": "user", "content": message}]

    try:
        # Для ответа в чате используем быструю модель (gpt-3.5-turbo) для снижения времени отклика
        resp = await chat_with_gpt(messages, temperature=0.7, max_tokens=1000, model="gpt-3.5-turbo")
    except Exception as e:
        logger.exception("Ошибка GPT")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка при вызове GPT: {e}"}

    answer = resp.get("text", "") or ""
    prompt_tokens = int(resp.get("prompt_tokens", 0))
    completion_tokens = int(resp.get("completion_tokens", 0))

    # Обновляем историю диалога в кеше
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer})
    await _save_history(user_id, student_id, history)

    return {
        "type": "chat",
        "task_id": task_id,
        "answer": answer,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "student_id": student_id
    }
