# worker/services/tasks_service.py
from __future__ import annotations

import logging
from typing import Dict, Any

from jinja2 import Template

from worker.services.generation_service import (
    generate_tasks_only,
    generate_solutions_for_tasks,
)
from worker.services.pdf_utils import (
    normalize_gpt_latex,
    compile_latex_to_b64,
)

logger = logging.getLogger(__name__)

# ====================== Красивые шаблоны XeLaTeX ======================

# PDF для ученика: только условия
STUDENT_TPL_SRC = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\setlist{noitemsep, topsep=4pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection.}{6pt}{}
\begin{document}

\begin{center}
{\LARGE Домашнее задание}
\end{center}
\vspace{0.6cm}

\section*{Задачи}
{\catcode`\^=12\relax \catcode`\_=12\relax
{{ tasks | safe }}
}

\end{document}
"""

# PDF для преподавателя: условия + решения
TEACHER_TPL_SRC = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\setlist{noitemsep, topsep=4pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection.}{6pt}{}
\begin{document}

\begin{center}
{\LARGE Домашнее задание — задачи и решения}
\end{center}
\vspace{0.6cm}

\section*{Задачи}
{\catcode`\^=12\relax \catcode`\_=12\relax
{{ tasks | safe }}
}

{% if solutions and solutions|length>0 %}
\vspace{0.4cm}
\section*{Решения}
{\catcode`\^=12\relax \catcode`\_=12\relax
{{ solutions | safe }}
}
{% endif %}

\end{document}
"""

STUDENT_TPL = Template(STUDENT_TPL_SRC)
TEACHER_TPL = Template(TEACHER_TPL_SRC)

def _cleanup_text(t: str) -> str:
    return (t or "").strip().replace("`", "")

# ====================== Основной обработчик ======================

async def handle_tasks(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    type='generate_tasks' — генерируем:
      1) PDF для ученика (только «Задачи»)
      2) PDF для преподавателя («Задачи» + «Решения»)
    Возвращаем ВСЕ совместимые поля:
      - tasks_text, solutions_text
      - tasks_pdf_b64 (Tasks.pdf), solutions_pdf_b64 (Solutions.pdf)
      - file (Tasks.pdf), solutions_file (Solutions.pdf) — для старых обработчиков бота
    """
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    prompt = (task.get("prompt") or task.get("description") or "").strip()
    count = int(task.get("count") or 10)
    count = max(1, min(15, count))

    logger.info("🔧 handle_tasks: task_id=%s", task_id)

    try:
        # 1) Сначала — чистые задания
        tgen = await generate_tasks_only(prompt, count=count)
        tasks_text = _cleanup_text(tgen.get("tasks_text", ""))
        if not tasks_text:
            return {"type": "error", "task_id": task_id, "message": "Генератор вернул пустой список задач."}

        # 2) Затем — решения для этих задач
        sgen = await generate_solutions_for_tasks(tasks_text)
        solutions_text = _cleanup_text(sgen.get("solutions_text", ""))

        # 3) Нормализация для LaTeX
        tasks_tex = normalize_gpt_latex(tasks_text)
        solutions_tex = normalize_gpt_latex(solutions_text) if solutions_text else ""

        # 4) Сборка двух PDF
        #   4.1 Студенческий (только задачи)
        student_latex = STUDENT_TPL.render(tasks=tasks_tex)
        tasks_pdf_b64, log1 = compile_latex_to_b64(student_latex, engine="xelatex")
        if not tasks_pdf_b64:
            logger.error("PDF Tasks compile error: %s", log1 or "compile failed")

        #   4.2 Преподавательский (задачи + решения)
        teacher_latex = TEACHER_TPL.render(tasks=tasks_tex, solutions=solutions_tex)
        solutions_pdf_b64, log2 = compile_latex_to_b64(teacher_latex, engine="xelatex")
        if not solutions_pdf_b64:
            logger.error("PDF Solutions compile error: %s", log2 or "compile failed")

        # 5) Результат — совместимые поля с прежней логикой бота
        result: Dict[str, Any] = {
            "type": "tasks",
            "task_id": task_id,
            "tasks_text": tasks_text,
            "solutions_text": solutions_text,
            "latex_tasks": student_latex,
            "latex_solutions": teacher_latex,
            # базовые поля:
            "tasks_pdf_b64": tasks_pdf_b64 or "",
            "solutions_pdf_b64": solutions_pdf_b64 or "",
            # совместимость со старым кодом бота:
            "file": tasks_pdf_b64 or "",            # раньше бот ожидал тут основной файл
            "solutions_file": solutions_pdf_b64 or "",  # сюда — файл с решениями
            # имена файлов (если где-то используются):
            "filename_tasks": "Tasks.pdf",
            "filename_solutions": "Solutions.pdf",
            # метрики:
            "prompt_tokens_tasks": int(tgen.get("prompt_tokens", 0)),
            "completion_tokens_tasks": int(tgen.get("completion_tokens", 0)),
            "prompt_tokens_solutions": int(sgen.get("prompt_tokens", 0)),
            "completion_tokens_solutions": int(sgen.get("completion_tokens", 0)),
        }
        return result

    except Exception as e:
        logger.exception("Ошибка в handle_tasks")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка генерации: {e}"}
