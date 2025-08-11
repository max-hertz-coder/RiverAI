import logging
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

_system_prompts = {
    'tasks': (
        "Вы — педагог-математик. Генерируйте ТОЛЬКО задания без решений и ответов. "
        "Создавайте ровно запрошенное количество задач с сохранением структуры (номеров и букв). "
        "НЕ включайте решения, ответы, пояснения или ход решения. "
        "Только условия задач в чистом виде. "
        "Используйте LaTeX для формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
    'solutions': (
        "Вы — педагог-математик. Пользователь прислал список задач с подпунктами a), b), c) и т.д.\n"
        "Верните ровно столько пунктов решения, сколько было задано (одно \\item на подпункт), "
        "но внутри каждого пункта **никакой дополнительной нумарации** и списков не должно быть. "
        "Каждое решение подавайте одним сплошным абзацем:\n"
        " 1) В начале одним предложением повторите условие подпункта.\n"
        " 2) Далее свободным текстом опишите ход решения без каких-либо меток «1.», «2.» и т.п.\n"
        " 3) В заключение чётко укажите итоговый ответ.\n"
        "Используйте LaTeX для всех формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
}

async def _async_call(prompt: str, role: str) -> dict:
    messages = [
        {"role": "system", "content": _system_prompts[role]},
        {"role": "user", "content": prompt},
    ]
    # Внутри chat_with_gpt параметр temperature будет отправлен только если модель это поддерживает
    resp = await chat_with_gpt(messages, temperature=0.0, max_tokens=6000)
    text = resp.get("text", "")
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
    return {
        "text": text,
        "prompt_tokens": int(resp.get("prompt_tokens", 0)),
        "completion_tokens": int(resp.get("completion_tokens", 0)),
        "total_tokens": int(resp.get("total_tokens", 0) or (resp.get("prompt_tokens", 0) + resp.get("completion_tokens", 0))),
    }

async def generate_raw_tasks(prompt: str) -> dict:
    return await _async_call(prompt, "tasks")

async def generate_raw_solutions(tasks: str) -> dict:
    return await _async_call(tasks, "solutions")

async def generate_solutions_continuation(original_sols: str, prompt: str) -> dict:
    full = (original_sols or "").strip() + "\n\n" + (prompt or "").strip()
    return await _async_call(full, "solutions")
