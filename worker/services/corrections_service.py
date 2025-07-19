import os
import asyncio
import openai
from worker.config import OPENAI_API_KEYS  # убедитесь, что в config.py есть эта константа

# Инициализируем ключ один раз при старте модуля
openai.api_key = OPENAI_API_KEYS


_corrections_prompt = (
    "Вы — редактор математических задач. Вам приходят две части: инструкция "
    "и raw-список задач (с LaTeX-разметкой). "
    "Примените только то, что указано в инструкции, сохраняя формат."
)

def _sync_correct(instruction: str, raw: str) -> str:
    full = instruction.strip() + "\n\n" + raw.strip()
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": _corrections_prompt},
            {"role": "user",   "content": full}
        ],
        temperature=0.0,
        max_tokens=800
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
    return text

async def generate_corrected_tasks(instruction: str, raw_tasks: str) -> str:
    return await asyncio.to_thread(_sync_correct, instruction, raw_tasks)
