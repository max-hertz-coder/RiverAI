import logging
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

_SYSTEM_TASKS = (
    "Вы — педагог-методист. Сгенерируйте ТОЛЬКО условия задач без решений и ответов. "
    "Нужен нумерованный список. Допускаются подпункты a), b), c). "
    "Формулы оформляйте в LaTeX: `$...$` или `\\[...\\]`. Не добавляйте комментариев."
)

_SYSTEM_SOLUTIONS = (
    "Вы — преподаватель. Даны условия задач с подпунктами. Верните решения в формате нумерованного списка, "
    "строго соответствующего исходным пунктам (одно \\item на подпункт), кратко и по делу. "
    "Формулы — в LaTeX. Без вводных фраз."
)

# «пинок» к структуре — если LLM «зависает» и молчит
_NUDGE = (
    "\n\nВАЖНО: Верните минимум 5 пунктов в нумерованном списке.\n"
    "1. [условие]\n2. [условие]\n3. [условие]\n4. [условие]\n5. [условие]\n"
    "Только условия, без решений и ответов."
)


async def _call_llm(messages, *, max_tokens=1500):
    """
    Вызываем chat_with_gpt без фиксации конкретной модели — даём шанс фолбэкам.
    """
    return await chat_with_gpt(messages, temperature=1.0, max_tokens=max_tokens, model=None, max_retries=3)


async def _safe_llm(system_prompt: str, user_prompt: str, *, nudge: bool = False) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt if not nudge else (user_prompt + _NUDGE)},
    ]
    resp = await _call_llm(messages, max_tokens=1800)
    text = (resp.get("text") or "").strip()

    # снимем обёртку из код-блоков
    if text.startswith("```") and text.endswith("```"):
        inner = text.strip("`\n")
        nl = inner.find("\n")
        text = inner[nl + 1 :] if nl != -1 else inner

    return text


async def generate_raw_tasks(prompt: str) -> dict:
    """
    Генерация только условий задач.
    """
    try:
        text = await _safe_llm(_SYSTEM_TASKS, prompt, nudge=False)
    except Exception:
        logger.warning("⚠️ Первая попытка генерации задач не удалась — пробую с NUDGE.")
        text = await _safe_llm(_SYSTEM_TASKS, prompt, nudge=True)

    return {"text": text or ""}


async def generate_raw_solutions(tasks: str) -> dict:
    """
    Генерация решений к условиям.
    """
    try:
        text = await _safe_llm(_SYSTEM_SOLUTIONS, tasks, nudge=False)
    except Exception:
        logger.warning("⚠️ Первая попытка генерации решений не удалась — пробую с NUDGE.")
        text = await _safe_llm(_SYSTEM_SOLUTIONS, tasks, nudge=True)

    return {"text": text or ""}


async def generate_solutions_continuation(original_sols: str, prompt: str) -> dict:
    full = (original_sols or "").strip() + "\n\n" + (prompt or "").strip()
    return await generate_raw_solutions(full)
