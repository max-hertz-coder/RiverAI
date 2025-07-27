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