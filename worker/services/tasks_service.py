import re, base64, logging
from worker.services import generation_service, pdf_utils
from worker.services.result_publisher import publish_result

logger = logging.getLogger(__name__)

async def handle_tasks(task: dict) -> None:
    task_id     = task.get("task_id")
    task_type   = task.get("type")
    prompt      = task.get("prompt", "").strip()
    raw_tasks   = task.get("tasks_text", "")

    try:
        if task_type == "generate_tasks":
            if not prompt:
                await publish_result({"task_id": task_id, "type": "error", "message": "Нет запроса."})
                return
            raw_tasks = await generation_service.generate_raw_tasks(prompt)
        elif task_type == "generate_solutions":
            if not raw_tasks:
                await publish_result({"task_id": task_id, "type": "error", "message": "Нет текста заданий."})
                return
        else:
            await publish_result({"task_id": task_id, "type": "error", "message": f"Некорректный тип: {task_type}"})
            return

        if not raw_tasks or raw_tasks.strip() == "":
            await publish_result({"task_id": task_id, "type": "error", "message": "Генератор вернул пусто."})
            return

        cleaned = re.sub(r'(?si)Варианты ответа:.*?(?=(?:\n\s*\d+\.\s)|\Z)', '', raw_tasks).strip()
        split_re = re.compile(r'(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)')
        tasks_list = [m.group(2).strip() for m in split_re.finditer(cleaned)] or [cleaned]

        solutions_text = await generation_service.generate_raw_solutions(cleaned)
        solutions_list = [m.group(2).strip() for m in split_re.finditer(solutions_text)] or []

        if len(solutions_list) != len(tasks_list):
            solutions_list = []
            for task_text in tasks_list:
                sol = (await generation_service.generate_raw_solutions(task_text)).strip()
                solutions_list.append(sol if sol else "*(решение не получено)*")

        solutions_list = pdf_utils.sanitize_solutions(solutions_list)
        items_tasks = "\n".join(f"\\item {pdf_utils.escape_latex(t)}" for t in tasks_list)
        items_solutions = "\n".join(f"\\item {pdf_utils.escape_latex(s)}" for s in solutions_list)

        latex_tasks = pdf_utils.template_basic.render(title="Задачи", content=items_tasks)
        latex_solutions = pdf_utils.template_solutions.render(
            content_tasks=items_tasks, content_solutions=items_solutions
        )

        pdf_t_path, log_t = pdf_utils.compile_latex_to_pdf(latex_tasks)
        pdf_s_path, log_s = pdf_utils.compile_latex_to_pdf(latex_solutions)

        if not pdf_t_path or not pdf_s_path:
            await publish_result({"task_id": task_id, "type": "error", "message": "Ошибка PDF-компиляции"})
            return

        with open(pdf_t_path, "rb") as f_t, open(pdf_s_path, "rb") as f_s:
            pdf_tasks_b64 = base64.b64encode(f_t.read()).decode()
            pdf_solutions_b64 = base64.b64encode(f_s.read()).decode()

        await publish_result({
            "task_id": task_id,
            "type": "tasks",
            "tasks_text": "\n\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks_list)),
            "file_tasks": pdf_tasks_b64,
            "file_solutions": pdf_solutions_b64
        })

    except Exception as e:
        logger.exception("🔴 Exception in handle_tasks")
        await publish_result({"task_id": task_id, "type": "error", "message": f"Ошибка генерации: {e}"})