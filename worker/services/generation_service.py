import os
import asyncio
import openai
from worker.config import OPENAI_API_KEYS  # убедитесь, что в config.py есть эта константа

# Инициализируем ключ один раз при старте модуля
openai.api_key = OPENAI_API_KEYS

_system_prompts = {
    "tasks": (
        "Вы — педагог-математик. Генерируйте ровно запрошенное количество задач, "
        "с сохранением структуры (номеров и букв), без лишних пояснений. "
        "Используйте LaTeX для формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
    "solutions": (
        "Вы — педагог-математик. Пользователь прислал список задач с подпунктами a), b), c) и т.д.\n"
        "Верните ровно столько пунктов решения, сколько было задано."
    ),
}

def _sync_call(prompt: str, role: str) -> str:
    messages = [
        {"role": "system",   "content": _system_prompts[role]},
        {"role": "user",     "content": prompt}
    ]
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.0,
        max_tokens=1500
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
    return text

async def generate_raw_tasks(prompt: str) -> str:
    return await asyncio.to_thread(_sync_call, prompt, "tasks")

async def generate_raw_solutions(tasks: str) -> str:
    return await asyncio.to_thread(_sync_call, tasks, "solutions")
