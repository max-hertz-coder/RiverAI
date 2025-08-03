import os
import asyncio
from openai import OpenAI

# Инициализируем клиент OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Системный промпт для универсальной правки задач из OnlyGPT
_corrections_prompt = (
    "Вы — редактор математических задач. Вам приходят две части: пользовательская инструкция"
    " и raw-список задач (с LaTeX-разметкой). "
    "Примените **только** то, что указано в инструкции, не меняя ничего лишнего: "
    "не трогайте другую нумерацию, не добавляйте вводных фраз, сохраните весь формат и LaTeX. "
    "Верните исправленный raw-список в том же формате."
)


def _sync_correct(instruction: str, raw: str) -> str:
    """
    Внутренняя синхронная функция для корректировки списка задач.
    """
    full_prompt = instruction.strip() + "\n\n" + raw.strip()
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": _corrections_prompt},
            {"role": "user",   "content": full_prompt}
        ],
        temperature=0.0,
        max_tokens=800
    )
    text = resp.choices[0].message.content.strip()
    # Убираем ```-обёртку, если есть
    if text.startswith("```") and text.endswith("```"):
        text = text.strip('`\n')
    return text


async def generate_corrected_tasks(instruction: str, raw_tasks: str) -> str:

    """
    Асинхронная обёртка для корректировки списка задач.
    """
    return await asyncio.to_thread(_sync_correct, instruction, raw_tasks)


import base64, logging
from worker.services import corrections_service

async def handle_correct_tasks(task: dict) -> dict:
    user_id = task["user_id"]
    student_id = task["student_id"]
    file_data = task.get("file_data")
    if not file_data:
        return {"type": "error", "user_id": user_id, "message": "Файл с заданиями не получен."}
    # Пытаемся извлечь текст заданий из файла
    try:
        file_bytes = base64.b64decode(file_data)
    except Exception as e:
        logging.error(f"Ошибка декодирования файла заданий: {e}")
        return {"type": "error", "user_id": user_id, "message": "Не удалось обработать файл заданий."}
    # Предполагаем текстовый файл:
    text = None
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Если файл не текстовый (PDF/DOCX) – возвращаем ошибку (в будущем можно добавить парсинг)
        return {"type": "error", "user_id": user_id, "message": "Формат файла не поддерживается. Загрузите текст или изображение."}
    # Инструкция по умолчанию для коррекции (можно расширить функциональность, запрашивая у пользователя, что исправить)
    instruction = "Исправьте ошибки и улучшите формулировки заданий, сохраняя исходный формат."
    try:
        corrected_text = await corrections_service.generate_corrected_tasks(instruction, text)
    except Exception as e:
        logging.error(f"Ошибка при генерации исправленных заданий: {e}")
        return {"type": "error", "user_id": user_id, "message": "Не удалось скорректировать задания."}
    corrected_text = corrected_text.strip() if corrected_text else "(без изменений)"
    return {
        "type": "tasks",
        "user_id": user_id,
        "student_id": student_id,
        "tasks_text": corrected_text
    }
