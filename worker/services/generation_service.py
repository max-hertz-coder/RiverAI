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

async def _safe_llm(system_prompt: str, user_prompt: str, *, nudge: bool = False, model: str = None, max_tokens: int = 1800) -> str:
    """
    Помощник для вызова chat_with_gpt с заданными системным и пользовательским промптом.
    Если nudge=True, добавляет в конец пользовательского промпта пример структуры (_NUDGE).
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt if not nudge else (user_prompt + _NUDGE)},
    ]
    resp = await chat_with_gpt(messages, temperature=1.0, max_tokens=max_tokens, model=model or None)
    text = (resp.get("text") or "").strip()
    # снимем обёртку из тройных кавычек (если модель вернула в формате кода)
    if text.startswith("```") and text.endswith("```"):
        inner = text.strip("`\n")
        nl = inner.find("\n")
        text = inner[nl + 1 :] if nl != -1 else inner
    return text

async def generate_raw_tasks(prompt: str) -> dict:
    """
    Генерация только условий задач (без решений).
    """
    try:
        # Используем быструю модель (gpt-3.5-turbo) для генерации условий задач
        text = await _safe_llm(_SYSTEM_TASKS, prompt.strip(), model="gpt-3.5-turbo", max_tokens=1800)
    except Exception:
        logger.warning("⚠️ Первая попытка генерации задач не удалась — пробую с подсказкой структуры (NUDGE).")
        text = await _safe_llm(_SYSTEM_TASKS, prompt.strip(), nudge=True, model="gpt-3.5-turbo", max_tokens=1800)
    return {"text": text or ""}

async def generate_raw_solutions(tasks: str) -> dict:
    """
    Генерация решений к заданным условиям задач.
    """
    try:
        # Используем быструю модель для генерации решений; увеличиваем лимит токенов для вместимости всех решений
        text = await _safe_llm(_SYSTEM_SOLUTIONS, tasks.strip(), model="gpt-3.5-turbo", max_tokens=3000)
    except Exception:
        logger.warning("⚠️ Первая попытка генерации решений не удалась — пробую с подсказкой (NUDGE).")
        text = await _safe_llm(_SYSTEM_SOLUTIONS, tasks.strip(), nudge=True, model="gpt-3.5-turbo", max_tokens=3000)
    return {"text": text or ""}

async def generate_solutions_continuation(original_sols: str, prompt: str) -> dict:
    """
    Догенерация решений по продолжению (объединяет уже полученные решения с новым запросом).
    """
    full_prompt = (original_sols or "").strip() + "\n\n" + (prompt or "").strip()
    # Продолжаем генерацию решений (использует ту же функцию generate_raw_solutions)
    return await generate_raw_solutions(full_prompt)
