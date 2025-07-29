# worker/tasks/gpt_generation.py

import logging
import re
import base64
import tempfile
from pathlib import Path

from worker.services.pdf_utils import compile_latex_to_pdf, escape_latex, sanitize_solutions, template_basic, template_solutions
from worker.services.ocr_service import extract_text_from_file
from worker.services.generation_module import generate_raw_tasks, generate_raw_solutions, generate_corrected_tasks

logger = logging.getLogger(__name__)


async def handle_generate_tasks(task: dict) -> dict:
    prompt = task.get("prompt", "")
    user_id = task.get("user_id")

    if not prompt or not user_id:
        return {"type": "error", "user_id": user_id, "message": "Недостаточно данных для генерации задач"}

    cleaned = re.sub(r'(?si)Варианты ответа:.*?(?=(?:\n\s*\d+\.\s)|\Z)', '', prompt).strip()
    split_re = re.compile(r'(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)')
    tasks = [m.group(2).strip() for m in split_re.finditer(cleaned)] or [cleaned]

    sols_raw = await generate_raw_solutions(cleaned)
    sols = [m.group(2).strip() for m in split_re.finditer(sols_raw)] or []

    if len(sols) != len(tasks):
        sols = [ (await generate_raw_solutions(t)).strip() for t in tasks ]
    sols = sanitize_solutions(sols)

    items_t = "\n".join(f"\\item {escape_latex(t)}" for t in tasks)
    items_s = "\n".join(f"\\item {escape_latex(s)}" for s in sols)

    latex_tasks     = template_basic.render(title="Задачи", content=items_t)
    latex_solutions = template_solutions.render(content_tasks=items_t, content_solutions=items_s)

    pdf_t, log_t = compile_latex_to_pdf(latex_tasks)
    pdf_s, log_s = compile_latex_to_pdf(latex_solutions)

    if not pdf_t or not pdf_s:
        return {"type": "error", "user_id": user_id, "message": "Не удалось сгенерировать PDF-файлы"}

    # Конвертируем в base64
    with open(pdf_t, "rb") as f1, open(pdf_s, "rb") as f2:
        pdf1_b64 = base64.b64encode(f1.read()).decode()
        pdf2_b64 = base64.b64encode(f2.read()).decode()

    return {
        "type": "tasks",
        "user_id": user_id,
        "file_tasks": pdf1_b64,
        "file_solutions": pdf2_b64
    }