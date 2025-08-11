
import os
import asyncio
import base64
import logging
from typing import Dict

from openai import OpenAI
from worker.services.tasks_service import handle_tasks  # ⟵ добавлено

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

# Системный промпт для универсальной правки задач из OnlyGPT
_SYSTEM_PROMPT = (
    "Вы — редактор математических задач. Вам приходят две части: пользовательская инструкция"
    " и raw-список задач (с LaTeX-разметкой). "
    "Примените **только** то, что указано в инструкции, не меняя ничего лишнего: "
    "не трогайте другую нумерацию, не добавляйте вводных фраз, сохраните весь формат и LaTeX. "
    "Верните исправленный raw-список в том же формате."
)




def _sync_correct(instruction: str, raw: str) -> str:
    full = (instruction or "").strip() + "\n\n" + (raw or "").strip()
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": full},
        ],
        temperature=0.0,
        max_tokens=4000,
    )
    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
    return text


async def generate_corrected_tasks(instruction: str, raw_tasks: str) -> str:
    return await asyncio.to_thread(_sync_correct, instruction, raw_tasks)


async def handle_correct_tasks(task: Dict) -> Dict:
    """
    Исправление задач:
      - возвращаем ПОЛНЫЙ результат, как в generate_solutions:
        LaTeX + PDF (base64) через reuse tasks_service.handle_tasks
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
            return {"type": "error", "task_id": task_id, "message": "Формат файла не поддерживается (нужен текст)."}

        corrected = (await generate_corrected_tasks(instruction or "Улучшите формулировки, сохранив формат.", raw_text)).strip()
        # ⟵ теперь прогоняем через pipeline генерации решений + PDF
        enriched = await handle_tasks({"task_id": task_id, "type": "generate_solutions", "tasks_text": corrected or raw_text})
        return enriched

    except Exception as e:
        logger.exception("Ошибка в handle_correct_tasks")
        return {"type": "error", "task_id": task_id, "message": f"Не удалось скорректировать задания: {e}"}
