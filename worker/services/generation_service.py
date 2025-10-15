# worker/services/generation_service.py
from __future__ import annotations

import logging
import re
from typing import Tuple

from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

# ======= Системные промпты (школьная программа, информативно и красиво) =======

_SYSTEM_COMBINED = (
    "Вы — опытный методист по школьной математике. "
    "Сгенерируйте набор задач и подробные решения к ним по запросу пользователя. "
    "Требования к задачам:\n"
    "• соответствуют школьной программе РФ; часть — базовый уровень, часть — средний, 1–2 — повышенный/олимпиадный;\n"
    "• формулировки краткие, без лишнего текста; \n"
    "• оформляйте математические выражения в LaTeX: $...$ или \\[ ... \\].\n\n"
    "ФОРМАТ ВЫВОДА СТРОГО такой (без лишних комментариев и преамбул):\n"
    "Задачи:\n"
    "1. ...\n"
    "2. ...\n"
    "...\n"
    "\n"
    "Решения:\n"
    "1. Краткое, но понятное решение с опорой на ключевые шаги. Итог оформляйте как \\(\\boxed{\\text{ответ}}\\).\n"
    "2. ...\n"
    "...\n"
)

# ======= Вспомогательные функции =======

def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        # уберём возможный язык после ```
        t = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", t)
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()

def _split_tasks_solutions(text: str) -> Tuple[str, str]:
    """
    Разбиваем по заголовкам "Задачи:" / "Решения:".
    Если модель вернёт в другом регистре — учитываем.
    """
    t = _strip_code_fences(text)
    # нормализуем
    t = t.replace("\r", "")
    # ищем секции
    m = re.split(r"\n\s*Решения\s*:\s*\n", t, flags=re.IGNORECASE)
    if len(m) == 2:
        left = re.sub(r"^\s*Задачи\s*:\s*\n", "", m[0], flags=re.IGNORECASE).strip()
        right = m[1].strip()
        return left, right

    # fallback: попробуем по ключевым словам
    idx = t.lower().find("решения")
    if idx != -1:
        left = t[:idx].replace("Задачи:", "").strip()
        right = t[idx:].replace("Решения:", "").strip()
        return left, right

    # если не нашли — считаем всё задачами
    return t, ""

# ======= Основные функции =======

async def generate_tasks_and_solutions(prompt: str, *, count: int = 10, language: str = "ru") -> dict:
    """
    Генерация задач и решений ОДНИМ вызовом (ускоряет отклик).
    count ограничиваем до 15.
    """
    count = max(1, min(15, int(count or 10)))
    user_prompt = (
        f"Нужно сгенерировать {count} задач(и) по запросу:\n{prompt.strip()}\n\n"
        "Не добавляйте оглавления и лишние разделы — строго следуйте формату."
    )

    # стараемся использовать turbo; fallback на общую цепочку в gpt_service
    resp = await chat_with_gpt(
        messages=[
            {"role": "system", "content": _SYSTEM_COMBINED},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=3500,   # хватает для 10–15 задач с краткими решениями
        model="gpt-5-turbo",
    )
    text = (resp.get("text") or "").strip()
    if not text:
        return {"text": "", "solutions": ""}

    tasks_text, solutions_text = _split_tasks_solutions(text)
    return {
        "text": tasks_text,
        "solutions": solutions_text,
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
    }

async def generate_only_tasks(prompt: str, *, count: int = 10) -> dict:
    """
    Если нужно только условия (без решений).
    """
    cnt = max(1, min(15, int(count or 10)))
    sys = (
        "Вы — методист. Сформулируйте ТОЛЬКО условия задач (без решений), "
        "соответствующие школьной программе; смесь базовых/средних и 1–2 повышенных. "
        "Кратко, по делу, LaTeX для формул. Формат: нумерованный список."
    )
    user = f"Нужно получить {cnt} задач(и) по теме/запросу:\n{prompt.strip()}"
    resp = await chat_with_gpt(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.7,
        max_tokens=1600,
        model="gpt-5-turbo",
    )
    return {"text": (resp.get("text") or "").strip()}
