# worker/services/generation_service.py
from __future__ import annotations

import logging
from typing import Dict

from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

# ====================== Промпт для ТОЛЬКО ЗАДАНИЙ ======================

_SYSTEM_TASKS_ONLY = (
    "Вы — опытный методист по школьной математике РФ. "
    "Сформулируйте ТОЛЬКО условия задач без решений. "
    "Требования:\n"
    "• соответствие школьной программе (5–11 классы, если не указано иное);\n"
    "• разнообразие типов: вычислительные, текстовые, на доказательство/свойства;\n"
    "• сочетание уровней: базовые, средние и 1–2 повышенные;\n"
    "• краткие формулировки, понятные ученику; математические выражения в LaTeX ($...$ или \\[...\\]).\n\n"
    "ФОРМАТ ВЫВОДА СТРОГО:\n"
    "Задачи:\n"
    "1. ...\n"
    "2. ...\n"
    "...\n"
    "Не добавляйте раздел «Решения», комментарии, предисловия и послесловия."
)

# ====================== Промпт для РЕШЕНИЙ К УЖЕ СУЩЕСТВУЮЩИМ ЗАДАНИЯМ ======================

_SYSTEM_SOLUTIONS = (
    "Вы — опытный преподаватель математики. "
    "Даны задачи, оформленные нумерованным списком. "
    "Напишите чёткие решения КАЖДОЙ из них, шаг за шагом, компактно, без воды. "
    "Формулы в LaTeX. Финальный ответ каждой задачи выделяйте как \\(\\boxed{\\text{...}}\\). "
    "ФОРМАТ ВЫВОДА СТРОГО:\n"
    "Решения:\n"
    "1. ...\n"
    "2. ...\n"
    "...\n"
    "Не повторяйте сами условия задач; выводите только решения."
)

def _cap(n: int, lo: int = 1, hi: int = 15) -> int:
    try:
        n = int(n)
    except Exception:
        n = lo
    return max(lo, min(hi, n))

# ====================== Публичные функции ======================

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
        max_tokens=1600,
        model="gpt-4-turbo",  # быстрый по умолчанию; фолбэки в gpt_service
    )
    text = (resp.get("text") or "").strip()
    return {
        "tasks_text": text,
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
        max_tokens=3000,  # решения объёмнее условий
        model="gpt-5",    # по умолчанию умный; фолбэк — в gpt_service
    )
    text = (resp.get("text") or "").strip()
    return {
        "solutions_text": text,
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
    }
