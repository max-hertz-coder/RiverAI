import re
import logging
import base64
from typing import Dict, List

from worker.services import generation_service, pdf_utils

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    if not isinstance(text, str):
        return ""
    s = text.strip()
    if s.startswith("```") and s.endswith("```"):
        return s.strip("`\n")
    return s


def _split_numbered(text: str) -> List[str]:
    """
    Делит по шаблону:
      1. ...
      2. ...
    Возвращает список пунктов без номеров.
    """
    split_re = re.compile(r"(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)")
    items = [m.group(2).strip() for m in split_re.finditer(text)]
    return items or [text.strip()]


def _remove_solutions_from_tasks(raw: str) -> str:
    """
    Удаляет блоки «Решение/Решения/Варианты ответа» и строки со словами
    «решение/ответ/рассмотрим/для этого».
    """
    cleaned = re.sub(
        r"(?si)(Решения?|Варианты ответа?):.*?(?=(?:\n\s*\d+\.\s)|\Z)", "", raw
    ).strip()

    filtered = []
    for line in cleaned.splitlines():
        low = line.lower()
        if not any(w in low for w in ("решение", "ответ", "рассмотрим", "для этого")):
            filtered.append(line)
    return "\n".join(filtered).strip()


async def handle_tasks(task: Dict) -> Dict:
    """
    Универсальная обработка:
      - generate_tasks: генерируем задания и решения, КОМПИЛИРУЕМ PDF и возвращаем base64
      - generate_solutions: принимаем raw_tasks -> генерируем решения -> КОМПИЛИРУЕМ PDF
    """
    task_id = task.get("task_id")
    task_type = (task.get("type") or "").strip()
    prompt = (task.get("prompt") or "").strip()
    raw_tasks = (task.get("tasks_text") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    try:
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # 1) Получаем сырой список задач
        if task_type == "generate_tasks":
            if not prompt:
                return {"task_id": task_id, "type": "error", "message": "Нет запроса."}

            logger.info("🔧 handle_tasks: промпт для генерации: %s", prompt[:200] + "…")
            t_resp = await generation_service.generate_raw_tasks(prompt)
            raw_tasks = _strip_code_fences(t_resp.get("text", ""))

            total_prompt_tokens += int(t_resp.get("prompt_tokens", 0))
            total_completion_tokens += int(t_resp.get("completion_tokens", 0))

        elif task_type == "generate_solutions":
            if not raw_tasks:
                return {"task_id": task_id, "type": "error", "message": "Нет текста заданий."}
        else:
            return {"task_id": task_id, "type": "error", "message": f"Некорректный тип: {task_type}"}

        if not raw_tasks:
            return {"task_id": task_id, "type": "error", "message": "Генератор вернул пусто."}

        logger.info("🔧 handle_tasks: исходный текст, длина: %d", len(raw_tasks))

        # 2) Очищаем задачи от решений/ответов
        cleaned = _remove_solutions_from_tasks(raw_tasks)
        logger.info("🔧 handle_tasks: после очистки, длина: %d", len(cleaned))

        tasks_list = _split_numbered(cleaned)

        # 3) Генерируем решения
        s_resp = await generation_service.generate_raw_solutions(cleaned)
        solutions_text = _strip_code_fences(s_resp.get("text", ""))

        total_prompt_tokens += int(s_resp.get("prompt_tokens", 0))
        total_completion_tokens += int(s_resp.get("completion_tokens", 0))

        solutions_list = _split_numbered(solutions_text)

        if len(solutions_list) != len(tasks_list):
            logger.warning(
                "Количество решений (%d) != количеству задач (%d). Догенерируем поштучно…",
                len(solutions_list), len(tasks_list),
            )
            solutions_list = []
            for item in tasks_list:
                one = await generation_service.generate_raw_solutions(item)
                text = _strip_code_fences(one.get("text", "")).strip() or "*(решение не получено)*"
                solutions_list.append(text)
                total_prompt_tokens += int(one.get("prompt_tokens", 0))
                total_completion_tokens += int(one.get("completion_tokens", 0))

        # 4) Санитизация и подготовка LaTeX
        solutions_list = pdf_utils.sanitize_solutions(solutions_list)
        items_tasks = "\n".join(f"\\item {pdf_utils.escape_latex(t)}" for t in tasks_list)
        items_solutions = "\n".join(f"\\item {pdf_utils.escape_latex(s)}" for s in solutions_list)

        latex_tasks = pdf_utils.template_basic.render(title="Задачи", content=items_tasks)
        latex_solutions = pdf_utils.template_solutions.render(
            content_tasks=items_tasks, content_solutions=items_solutions
        )

        # 5) КОМПИЛЯЦИЯ PDF на воркере → base64
        tasks_pdf_b64, log_t = pdf_utils.compile_latex_to_b64(latex_tasks)
        solutions_pdf_b64, log_s = pdf_utils.compile_latex_to_b64(latex_solutions)

        if not tasks_pdf_b64 or not solutions_pdf_b64:
            logger.error("PDF compile error. tasks_log_len=%d, sol_log_len=%d", len(log_t), len(log_s))

        return {
            "task_id": task_id,
            "type": "tasks",
            "tasks_text": "\n\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks_list)),
            "latex_tasks": latex_tasks,
            "latex_solutions": latex_solutions,
            "tasks_pdf_b64": tasks_pdf_b64,
            "solutions_pdf_b64": solutions_pdf_b64,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
        }

    except Exception as e:
        logger.exception("🔴 Exception in handle_tasks")
        return {"task_id": task_id, "type": "error", "message": f"Ошибка генерации: {e}"}
