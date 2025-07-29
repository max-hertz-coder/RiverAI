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
    Возвращает raw_tasks_text и два файла в base64: file_tasks и file_solutions.
    """
    user_id = task.get("user_id")
    prompt = (task.get("prompt") or "").strip()
    student_id = task.get("student_id")

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
            r'(?si)Варианты ответа:.*?(?=(?:\n\s*\d+\.|\Z))',
            '',
            raw_tasks
        ).strip()
        split_re = re.compile(r'(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)')
        tasks_list = [m.group(2).strip() for m in split_re.finditer(cleaned)] or [cleaned]

        # 3. Собираем текст для отправки в чат (с номерами)
        raw_tasks_text = "\n\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks_list))

        # 4. Генерируем решения для всего списка задач сразу
        sols_raw = await generate_raw_solutions(cleaned)
        solutions_list = [m.group(2).strip() for m in split_re.finditer(sols_raw)] or []
        if len(solutions_list) != len(tasks_list):
            solutions_list = []
            for t in tasks_list:
                sol = (await generate_raw_solutions(t)).strip()
                solutions_list.append(sol or "*(решение не получено)*")

        # 5. Санитизируем решения
        solutions_list = sanitize_solutions(solutions_list)

        # 6. Подготавливаем LaTeX-контент
        items_t = "\n".join(f"\\item {escape_latex(t)}" for t in tasks_list)
        items_s = "\n".join(f"\\item {escape_latex(s)}" for s in solutions_list)
        latex_tasks = template_basic.render(title="Задачи", content=items_t)
        latex_solutions = template_solutions.render(
            content_tasks=items_t,
            content_solutions=items_s
        )

        # 7. Компилируем PDF
        pdf_t_path, log_t = compile_latex_to_pdf(latex_tasks)
        pdf_s_path, log_s = compile_latex_to_pdf(latex_solutions)
        if not pdf_t_path or not pdf_s_path:
            logger.error("LaTeX compile errors:\nTasks: %s\nSolutions: %s", log_t, log_s)
            return {
                "type": "error",
                "user_id": user_id,
                "message": "Не удалось сгенерировать PDF-файлы."
            }

        # 8. Кодируем PDF в base64
        with open(pdf_t_path, "rb") as f1, open(pdf_s_path, "rb") as f2:
            pdf_tasks_b64 = base64.b64encode(f1.read()).decode()
            pdf_solutions_b64 = base64.b64encode(f2.read()).decode()

        # 9. Удаляем временные файлы
        Path(pdf_t_path).unlink(missing_ok=True)
        Path(pdf_s_path).unlink(missing_ok=True)

        # 10. Возвращаем результат
        return {
            "type": "tasks",
            "user_id": user_id,
            "student_id": student_id,
            "raw_tasks_text": raw_tasks_text,
            "file": pdf_tasks_b64,
            "file_solutions": pdf_solutions_b64
        }

    except Exception as e:
        logger.exception("Ошибка в handle_generate_tasks: %s", e)
        return {
            "type": "error",
            "user_id": user_id,
            "message": f"Ошибка при генерации заданий: {e}"
        }
