import logging
import re
import base64
from pathlib import Path

from worker.services.pdf_utils import (
    compile_latex_to_pdf, escape_latex,
    sanitize_solutions, template_basic, template_solutions
)
from worker.services.generation_services import (
    generate_raw_tasks, generate_raw_solutions
)

logger = logging.getLogger(__name__)

async def handle_generate_tasks(task: dict) -> dict:
    """
    Генерация PDF-файлов с задачами и решениями по заданному запросу.
    Возвращает два файла в base64: file_tasks и file_solutions.
    """
    user_id = task.get("user_id")
    prompt = task.get("prompt", "").strip()

    if not prompt or not user_id:
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Недостаточно данных для генерации задач."
        }

    try:
        # 1. Генерируем сырой список задач
        raw_tasks = await generate_raw_tasks(prompt)
        if not raw_tasks or not raw_tasks.strip():
            return {
                "type": "error",
                "user_id": user_id,
                "message": "Генератор вернул пустой список задач."
            }

        # 2. Очищаем от вариантов ответов и разбиваем на отдельные задачи
        cleaned = re.sub(
            r'(?si)Варианты ответа:.*?(?=(?:\n\s*\d+\.\s)|\Z)',
            '',
            raw_tasks
        ).strip()
        split_re = re.compile(r'(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)')
        tasks_list = [
            m.group(2).strip()
            for m in split_re.finditer(cleaned)
        ] or [cleaned]

        # 3. Генерируем решения для всего списка задач сразу
        sols_raw = await generate_raw_solutions(cleaned)
        solutions_list = [
            m.group(2).strip()
            for m in split_re.finditer(sols_raw)
        ] or []
        # Если число решений не совпадает с числом задач, генерируем по отдельности
        if len(solutions_list) != len(tasks_list):
            solutions_list = []
            for t in tasks_list:
                sol = (await generate_raw_solutions(t)).strip()
                solutions_list.append(sol or "*(решение не получено)*")

        # 4. Санитизируем решения (удаляем маркеры itemize и \item)
        solutions_list = sanitize_solutions(solutions_list)

        # 5. Подготавливаем LaTeX-контент
        items_t = "\n".join(
            f"\\item {escape_latex(t)}" for t in tasks_list
        )
        items_s = "\n".join(
            f"\\item {escape_latex(s)}" for s in solutions_list
        )

        # 6. Компилируем PDF для задач и для задач+решений
        latex_tasks = template_basic.render(title="Задачи", content=items_t)
        latex_solutions = template_solutions.render(
            content_tasks=items_t,
            content_solutions=items_s
        )
        pdf_t_path, log_t = compile_latex_to_pdf(latex_tasks)
        pdf_s_path, log_s = compile_latex_to_pdf(latex_solutions)

        if not pdf_t_path or not pdf_s_path:
            logger.error("LaTeX compile errors:\nTasks: %s\nSolutions: %s", log_t, log_s)
            return {
                "type": "error",
                "user_id": user_id,
                "message": "Не удалось сгенерировать PDF-файлы."
            }

        # 7. Кодируем оба PDF в base64
        with open(pdf_t_path, "rb") as f_t, open(pdf_s_path, "rb") as f_s:
            pdf_tasks_b64 = base64.b64encode(f_t.read()).decode()
            pdf_solutions_b64 = base64.b64encode(f_s.read()).decode()

        # 8. Удаляем временные файлы
        Path(pdf_t_path).unlink(missing_ok=True)
        Path(pdf_s_path).unlink(missing_ok=True)

        return {
            "type": "tasks",
            "user_id": user_id,
            "file_tasks": pdf_tasks_b64,
            "file_solutions": pdf_solutions_b64
        }

    except Exception as e:
        logger.exception("Ошибка в handle_generate_tasks")
        return {
            "type": "error",
            "user_id": user_id,
            "message": f"Ошибка при генерации заданий: {e}"
        }