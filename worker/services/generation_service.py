# worker/services/generation_service.py
from __future__ import annotations

import logging
from typing import Dict

from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

# =============== Промпт для ТОЛЬКО ЗАДАНИЙ (ученику) ===============

_SYSTEM_TASKS_ONLY = (
    "Вы — опытный методист по школьной математике РФ. "
    "Сформулируйте ТОЛЬКО условия задач без решений.\n"
    "Требования:\n"
    "• соответствие школьной программе (5–11 классы, если не указано иное);\n"
    "• разнообразие типов: вычислительные, текстовые, на свойства/доказательства;\n"
    "• кратко и понятно ученику; формулы в LaTeX ($...$ или \\[...\\]).\n\n"
    "ФОРМАТ ВЫВОДА СТРОГО:\n"
    "Задачи:\n"
    "1. ...\n"
    "2. ...\n"
    "...\n"
    "Каждую задачу начинайте с новой строки, не сливайте в одну строку.\n"
    "Не добавляйте раздел «Решения», комментарии, оглавления и т.д."
)

# =============== Промпт для РЕШЕНИЙ (преподавателю) ===============

_SYSTEM_SOLUTIONS = (
    "Вы — опытный преподаватель математики. Даны задачи (нумерованный список). "
    "Напишите чёткие решения КАЖДОЙ из них: по шагам, компактно, без воды. "
    "Формулы в LaTeX; итог каждого решения выделяйте как \\(\\boxed{\\text{...}}\\).\n\n"
    "ФОРМАТ ВЫВОДА СТРОГО:\n"
    "Решения:\n"
    "1. ...\n"
    "2. ...\n"
    "...\n"
    "Не повторяйте сами условия задач; выводите только решения, по одному пункту на новую строку."
)

def _cap(n: int, lo: int = 1, hi: int = 15) -> int:
    try:
        n = int(n)
    except Exception:
        n = lo
    return max(lo, min(hi, n))

# =============== Публичные функции ===============

async def generate_tasks_only(prompt: str, *, count: int = 10) -> Dict[str, str]:
    """
    Генерирует ТОЛЬКО условия задач (без решений).
    """
    cnt = _cap(count)
    user_prompt = (
        f"Нужно получить {cnt} задач(и) по запросу/теме:\n{prompt.strip()}\n\n"
        "Строго следуйте требуемому формату."
    )
    resp = await chat_with_gpt(
        messages=[
            {"role": "system", "content": _SYSTEM_TASKS_ONLY},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=1400,            # достаточно для 15 кратких задач
        model="gpt-4-turbo",        # быстрый дефолт; фолбэки настроены
        request_timeout=50.0,
    )
    return {
        "tasks_text": (resp.get("text") or "").strip(),
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
    }

async def generate_solutions_for_tasks(tasks_text: str) -> Dict[str, str]:
    """
    Принимает уже готовые задачи (нумерованный список) и генерирует ТОЛЬКО раздел «Решения: ...».
    """
    if not (tasks_text or "").strip():
        return {"solutions_text": ""}

    user_prompt = "Вот список задач. Напишите решения по указанным правилам.\n\n" + tasks_text.strip()
    resp = await chat_with_gpt(
        messages=[
            {"role": "system", "content": _SYSTEM_SOLUTIONS},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2600,            # решения объёмнее условий
        model="gpt-4-turbo",        # стартуем с gpt-4-turbo, чтобы избежать 401/empty на gpt-5
        request_timeout=55.0,
    )
    return {
        "solutions_text": (resp.get("text") or "").strip(),
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
    }
