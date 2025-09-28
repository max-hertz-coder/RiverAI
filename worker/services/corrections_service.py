import os
import asyncio
import base64
import logging
from typing import Dict

from openai import OpenAI
from worker.services.tasks_service import handle_tasks  # reuse pipeline

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Вы — редактор математических задач. Вам приходят две части: пользовательская инструкция "
    "и raw-список задач (с LaTeX-разметкой). "
    "Примените ТОЛЬКО то, что указано в инструкции, сохранив нумерацию, разметку и структуру. "
    "Не добавляйте вводных фраз. Верните исправленный raw-список в том же формате."
)

def _sync_correct(instruction: str, raw: str) -> str:
    """
    Синхронный вызов OpenAI для правок raw-задач.
    ВАЖНО: для gpt-5(-mini) используем temperature=1.0 и max_completion_tokens.
    """
    full = (instruction or "").strip() + "\n\n" + (raw or "").strip()
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": full},
        ],
        temperature=1.0,            # ⟵ fix: 0.0 запрещён у gpt-5(-mini)
        max_completion_tokens=800,  # ⟵ корректный параметр для новых моделей
    )
    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl+1:]
    return text

async def generate_corrected_tasks(instruction: str, raw_tasks: str) -> str:
    return await asyncio.to_thread(_sync_correct, instruction, raw_tasks)

async def handle_correct_tasks(task: Dict) -> Dict:
    """
    Исправление задач с последующей сборкой PDF-ов (задачи+решения) через общий pipeline.
    """
    task_id = task.get("task_id")
    instruction = (task.get("prompt") or "").strip()
    file_data = task.get("file_data")

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    if not file_data:
        return {"type": "error", "task_id": task_id, "message": "Файл с заданиями не получен."}

    try:
        content = base64.b64decode(file_data)
        try:
            raw_text = content.decode("utf-8")
        except UnicodeDecodeError:
            return {"type": "error", "task_id": task_id, "message": "Формат файла не поддерживается (ожидается текст)."}

        corrected = (await generate_corrected_tasks(instruction or "Улучшите формулировки, сохранив формат.", raw_text)).strip()
        enriched = await handle_tasks({
            "task_id": task_id,
            "type": "generate_solutions",
            "tasks_text": corrected or raw_text
        })
        return enriched

    except Exception as e:
        logger.exception("Ошибка в handle_correct_tasks")
        return {"type": "error", "task_id": task_id, "message": f"Не удалось скорректировать задания: {e}"}
