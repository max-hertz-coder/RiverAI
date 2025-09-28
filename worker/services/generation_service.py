import logging
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

# Системные подсказки под разные роли
_system_prompts = {
    "tasks": (
        "Вы — педагог-математик. Сгенерируйте ТОЛЬКО задания без решений и ответов.\n"
        "Создайте ровно запрошенное количество задач с сохранением структуры (номеров и подпунктов a), b), c)).\n"
        "НЕ включайте решения, ответы, пояснения или ход решения.\n"
        "Только условия задач в чистом виде.\n"
        "Используйте LaTeX для формул: `$...$` для inline и `\\[...\\]` для display."
    ),
    "solutions": (
        "Вы — педагог-математик. Пользователь прислал список задач с подпунктами a), b), c).\n"
        "Верните ровно столько пунктов решения, сколько было задано (одно \\item на подпункт), "
        "без вложенных списков и дополнительной нумерации.\n"
        "Каждое решение — один абзац: кратко повторите условие подпункта, затем ход решения, затем итоговый ответ.\n"
        "Используйте LaTeX для формул (`$...$` и `\\[...\\]`)."
    ),
}

_FALLBACK_NUDGE = (
    "\n\nВАЖНО: Верните как минимум 5 нумерованных задач в формате:\n"
    "1. [условие]\n"
    "2. [условие]\n"
    "...\n"
    "Только список условий, без решений."
)


async def _async_call(prompt: str, role: str) -> dict:
    """
    Базовый вызов GPT с повтором, если ответ пустой.
    Сначала пробуем gpt-5-mini, если пусто — пробуем gpt-5.
    Если снова пусто — добавляем «пинок-промпт» и пробуем ещё раз.
    """
    messages = [
        {"role": "system", "content": _system_prompts[role]},
        {"role": "user", "content": prompt},
    ]

    # 1) Первая попытка (mini)
    resp = await chat_with_gpt(messages, temperature=1.0, max_tokens=1500, model="gpt-5-mini")
    text = (resp.get("text") or "").strip()

    # 2) Если пусто — пробуем обычный gpt-5
    if not text:
        logger.warning("⚠️ Пустой ответ от GPT (mini). Повтор с model=gpt-5")
        resp = await chat_with_gpt(messages, temperature=1.0, max_tokens=1500, model="gpt-5")
        text = (resp.get("text") or "").strip()

    # 3) Если всё ещё пусто — «пинок» к структуре
    if not text:
        logger.warning("⚠️ Снова пусто. Добавляю инструкцию-напоминание о структуре и повторяю.")
        messages[-1]["content"] = prompt + _FALLBACK_NUDGE
        resp = await chat_with_gpt(messages, temperature=1.0, max_tokens=1500, model="gpt-5")
        text = (resp.get("text") or "").strip()

    # 4) Снимаем тройные бэктики, если LLM вернул код-блок
    if text.startswith("```") and text.endswith("```"):
        inner = text.strip("`\n")
        first_nl = inner.find("\n")
        text = inner[first_nl + 1 :] if first_nl != -1 else inner

    return {
        "text": text,
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
        "total_tokens": int(
            resp.get("total_tokens", 0)
            or (int(resp.get("prompt_tokens", 0)) + int(resp.get("completion_tokens", 0)))
        ),
    }


async def generate_raw_tasks(prompt: str) -> dict:
    return await _async_call(prompt, "tasks")


async def generate_raw_solutions(tasks: str) -> dict:
    return await _async_call(tasks, "solutions")


async def generate_solutions_continuation(original_sols: str, prompt: str) -> dict:
    full = (original_sols or "").strip() + "\n\n" + (prompt or "").strip()
    return await _async_call(full, "solutions")
