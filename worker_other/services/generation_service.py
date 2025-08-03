import os
import asyncio
from openai import OpenAI

# Инициализируем клиент OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Системные подсказки под разные роли из OnlyGPT
_system_prompts = {
    'tasks': (
        "Вы — педагог-математик. Генерируйте ровно запрошенное количество задач, "
        "с сохранением структуры (номеров и букв), без лишних пояснений. "
        "Используйте LaTeX для формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
    'solutions': (
        "Вы — педагог-математик. Пользователь прислал список задач с подпунктами a), b), c) и т.д.\n"
        "Верните ровно столько пунктов решения, сколько было задано (одно \\item на подпункт), "
        "но внутри каждого пункта **никакой дополнительной нумерации** и списков не должно быть. "
        "Каждое решение подавайте одним сплошным абзацем:\n"
        " 1) В начале одним предложением повторите условие подпункта.\n"
        " 2) Далее свободным текстом опишите ход решения без каких-либо меток «1.», «2.» и т.п.\n"
        " 3) В заключение чётко укажите итоговый ответ.\n"
        "Используйте LaTeX для всех формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
}


def _sync_call(prompt: str, role: str) -> str:
    """
    Внутренняя синхронная функция для обращения к OpenAI по роли.
    """
    messages = [
        {"role": "system", "content": _system_prompts[role]},
        {"role": "user",   "content": prompt}
    ]
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.0,
        max_tokens=1500
    )
    text = resp.choices[0].message.content.strip()
    # Убираем ```-обёртку, если есть
    if text.startswith("```") and text.endswith("```"):
        text = text.strip('`\n')
    return text


async def generate_raw_tasks(prompt: str) -> str:
    """Генерирует список задач по запросу."""
    return await asyncio.to_thread(_sync_call, prompt, 'tasks')

async def generate_raw_solutions(tasks: str) -> str:
    """Генерирует решения к списку задач."""
    return await asyncio.to_thread(_sync_call, tasks, 'solutions')

async def generate_solutions_continuation(original_sols: str, prompt: str) -> str:
    """
    Продолжает генерацию решений на основании уже полученных.
    """
    full = original_sols.strip() + "\n\n" + prompt.strip()
    return await asyncio.to_thread(_sync_call, full, 'solutions')