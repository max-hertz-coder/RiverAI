import os
import asyncio
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

# Системные подсказки под разные роли
_system_prompts = {
    'tasks': (
        "Вы — педагог-математик. Генерируйте ровно запрошенное количество задач, "
        "с сохранением структуры (номеров и букв), без лишних пояснений. "
        "Используйте LaTeX для формул (`$...$` для inline, `\\[...\\]` для display)."
    ),
    'solutions': (
        "Вы — педагог-математик. Пользователь прислал список задач с подпунктами a), b), c) и т.д.\n"
        "Верните ровно столько пунктов решения, сколько было задано, "
        "но внутри каждого пункта **никакой дополнительной нумерации** и списков не должно быть. "
        "Каждое решение подавайте одним сплошным абзацем:\n"
        " 1) В начале одним предложением повторите условие подпункта.\n"
        " 2) Далее свободным текстом опишите ход решения без каких-либо меток «1.», «2.» и т.п.\n"
        " 3) В заключение чётко укажите итоговый ответ.\n"
        "Используйте LaTeX для всех формул (`$...$` для inline, `\\[...\\]` для display). "
        "ВАЖНО: Не помещайте русский текст внутрь математических выражений ($...$ или \\[...\\]). "
        "Русский текст должен быть вне математических выражений. "
        "НЕ используйте никакие LaTeX команды для структурирования (\\begin{...}, \\end{...}, \\item). "
        "Просто пишите чистый текст решения с математическими формулами."
    ),
}

def _sync_call(prompt: str, role: str) -> str:
    """
    Синхронный вызов ChatCompletion с указанным системным промптом.
    """
    messages = [
        {"role": "system", "content": _system_prompts[role]},
        {"role": "user",   "content": prompt}
    ]
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.0,
        max_tokens=1500
    )
    text = resp.choices[0].message.content.strip()
    # Убираем ``` если есть
    if text.startswith("```") and text.endswith("```"):
        text = text.strip('`\n')
    return text

async def generate_raw_tasks(prompt: str) -> str:
    """Генерирует список задач по запросу."""
    return await asyncio.to_thread(_sync_call, prompt, 'tasks')

async def generate_raw_solutions(tasks: str) -> str:
    """Генерирует решения к списку задач."""
    return await asyncio.to_thread(_sync_call, tasks, 'solutions')

async def handle_generate_tasks(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи генерации заданий.
    Принимает task с полями: task_id, prompt (запрос пользователя)
    Возвращает сгенерированные задания.
    """
    task_id = task.get("task_id")
    prompt = task.get("prompt", "").strip()
    
    logger.info(f"🔧 Обрабатываем задачу generate_tasks: task_id={task_id}, prompt_length={len(prompt)}")
    
    if not task_id:
        logger.error("❌ Отсутствует task_id в задаче generate_tasks")
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not prompt:
        logger.error("❌ Нет запроса для генерации в задаче generate_tasks")
        return {"type": "error", "message": "Нет запроса для генерации."}
    
    try:
        logger.info(f"🔧 Генерируем задания: task_id={task_id}")
        
        # Генерируем задания
        raw_tasks = await generate_raw_tasks(prompt)
        
        logger.info(f"✅ Сгенерированы задания: task_id={task_id}, tasks_length={len(raw_tasks)}")
        
        return {
            "type": "generate_tasks",
            "task_id": task_id,
            "prompt": prompt,
            "raw_tasks": raw_tasks
        }
        
    except Exception as e:
        logger.exception(f"❌ Ошибка в handle_generate_tasks для task_id={task_id}: {e}")
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при генерации заданий: {str(e)}"
        }