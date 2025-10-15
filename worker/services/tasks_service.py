# worker/services/tasks_service.py
from __future__ import annotations

import logging
from typing import Dict, Any

from jinja2 import Template
from worker.services.generation_service import (
    generate_tasks_and_solutions,
    generate_only_tasks,
)
from worker.services.pdf_utils import (
    normalize_gpt_latex,
    compile_latex_to_b64,
)

logger = logging.getLogger(__name__)

# Красивый XeLaTeX-шаблон: «Задачи» + «Решения»
DOC_TPL = r"""
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
{\LARGE Задачи и решения}
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
TPL = Template(DOC_TPL)


def _cleanup_text(t: str) -> str:
    """
    Убираем бэктики/мусор, чуть нормализуем для LaTeX.
    """
    t = (t or "").strip().replace("`", "")
    return t


async def handle_tasks(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Универсальный обработчик генерации:
      • type='generate_tasks'  — генерим задачи И решения ОДНИМ вызовом (быстрее)
      • type='generate_solutions' — оставлен для совместимости (ожидает tasks_text)
    На выход отдаём:
      • 'file' — общий PDF (base64)
      • 'solutions_file' — то же самое (совместимость с ботом)
      • 'solutions_pdf_b64' / 'tasks_pdf_b64' — на всякий случай для старого кода
    """
    task_id = task.get("task_id")
    task_type = (task.get("type") or "").strip()
    prompt = (task.get("prompt") or task.get("description") or "").strip()
    only = bool(task.get("only_tasks") or False)
    count = int(task.get("count") or 10)
    count = max(1, min(15, count))

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    try:
        # ===== 1) Генерация контента =====
        if task_type == "generate_solutions":
            # Совместимость: если передали только решения для уже имеющихся задач — сгенерируй только условия
            raw_tasks = (task.get("tasks_text") or "").strip()
            if not raw_tasks:
                # не прислали задания — сгенерируем и задачи, и решения
                only = False

        if only:
            r = await generate_only_tasks(prompt, count=count)
            tasks_text = _cleanup_text(r.get("text", ""))
            solutions_text = ""
            prompt_tokens = int(r.get("prompt_tokens", 0))
            completion_tokens = int(r.get("completion_tokens", 0))
        else:
            r = await generate_tasks_and_solutions(prompt, count=count)
            tasks_text = _cleanup_text(r.get("text", ""))
            solutions_text = _cleanup_text(r.get("solutions", ""))
            prompt_tokens = int(r.get("prompt_tokens", 0))
            completion_tokens = int(r.get("completion_tokens", 0))

        if not tasks_text:
            return {"type": "error", "task_id": task_id, "message": "Генератор вернул пустой текст задач."}

        # ===== 2) Подготовка для LaTeX =====
        tasks_tex = normalize_gpt_latex(tasks_text)
        solutions_tex = normalize_gpt_latex(solutions_text) if solutions_text else ""

        latex_full = TPL.render(tasks=tasks_tex, solutions=solutions_tex)

        # ===== 3) Компиляция PDF =====
        file_b64, log = compile_latex_to_b64(latex_full, engine="xelatex")
        if not file_b64:
            logger.error("PDF compile error: %s", log or "compile failed")

        # Для совместимости со старым кодом бота — дублируем в несколько ключей
        result: Dict[str, Any] = {
            "type": "tasks",
            "task_id": task_id,
            "tasks_text": tasks_text,
            "solutions_text": solutions_text,
            "latex_content": latex_full,
            # общий PDF
            "file": file_b64 or "",
            # старые обработчики могли смотреть сюда
            "solutions_file": file_b64 or "",
            # и на эти ключи
            "solutions_pdf_b64": file_b64 or "",
            "tasks_pdf_b64": file_b64 or "",
            # метрики
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        return result

    except Exception as e:
        logger.exception("Ошибка в handle_tasks")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка генерации: {e}"}
