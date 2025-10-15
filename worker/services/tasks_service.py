# worker/services/tasks_service.py
from __future__ import annotations

import logging
import re
from typing import Dict, Any, List

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

# Студент: только задачи
STUDENT_TPL_SRC = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\setlist{noitemsep, topsep=6pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection.}{6pt}{}
\begin{document}

\begin{center}
{\LARGE Домашнее задание}
\end{center}
\vspace{0.6cm}

\section*{Задачи}
\begin{enumerate}[leftmargin=*, itemsep=8pt]
{{ tasks_items | safe }}
\end{enumerate}

\end{document}
"""

# Преподаватель: задачи + решения
TEACHER_TPL_SRC = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\setlist{noitemsep, topsep=6pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection.}{6pt}{}
\begin{document}

\begin{center}
{\LARGE Домашнее задание — задачи и решения}
\end{center}
\vspace{0.6cm}

\section*{Задачи}
\begin{enumerate}[leftmargin=*, itemsep=8pt]
{{ tasks_items | safe }}
\end{enumerate}

{% if solutions_items and solutions_items|length>0 %}
\vspace{0.4cm}
\section*{Решения}
\begin{enumerate}[leftmargin=*, itemsep=10pt]
{{ solutions_items | safe }}
\end{enumerate}
{% endif %}

\end{document}
"""

STUDENT_TPL = Template(STUDENT_TPL_SRC)
TEACHER_TPL = Template(TEACHER_TPL_SRC)

# ====================== Утилиты форматирования ======================

_HEADER_RX = re.compile(r"^\s*(Задачи:|Решения:)\s*", re.IGNORECASE)

def _strip_header(text: str) -> str:
    return _HEADER_RX.sub("", (text or "").strip())

def _split_numbered(text: str) -> List[str]:
    """
    Разбивает «1. ... 2. ... 3. ...» даже если всё пришло в ОДНУ строку.
    Не привязываемся к переносам; ищем любые «N. » и режем.
    """
    t = _strip_header(text)
    # вставим разделители перед каждым " N. "
    t = re.sub(r"(?<!\d)(\s|^)(\d+)\.\s+", r"\1|||", t)
    parts = [p.strip() for p in t.split("|||") if p.strip()]
    # если GPT начал не с "1. ...", первая часть может быть мусором — выкинем её
    if parts and not re.match(r"^\d+\.", parts[0]):
        parts = [p for p in parts if not p.isdigit()]  # на всякий
    # уберём префикс "N. " внутри элементов
    cleaned: List[str] = []
    for p in parts:
        cleaned.append(re.sub(r"^\d+\.\s*", "", p))
    return cleaned

def _items_to_latex(items: List[str]) -> str:
    """
    Превращает список пунктов в набор \item ... c лёгкой нормализацией LaTeX.
    """
    out: List[str] = []
    for it in items:
        it_norm = normalize_gpt_latex(it.strip())
        # доп. разрыв абзаца внутри пункта, если много текста
        it_norm = it_norm.replace("\n\n", "\n\\par\n")
        out.append("\\item " + it_norm)
    return "\n".join(out)

def _cleanup_text(t: str) -> str:
    return (t or "").replace("`", "").strip()

# ====================== Основной обработчик ======================

async def handle_tasks(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    type='generate_tasks' — генерируем:
      1) PDF для ученика (только «Задачи»)
      2) PDF для преподавателя («Задачи» + «Решения»)
    Возвращаем совместимые поля:
      - tasks_text, solutions_text
      - tasks_pdf_b64 (Tasks.pdf), solutions_pdf_b64 (Solutions.pdf)
      - file (Tasks.pdf), solutions_file (Solutions.pdf)
    """
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    prompt = (task.get("prompt") or task.get("description") or "").strip()
    count = int(task.get("count") or 10)
    count = max(1, min(15, count))

    logger.info("🔧 handle_tasks: task_id=%s", task_id)

    try:
        # 1) Задания (ученику)
        tgen = await generate_tasks_only(prompt, count=count)
        tasks_text_raw = _cleanup_text(tgen.get("tasks_text", ""))
        if not tasks_text_raw:
            return {"type": "error", "task_id": task_id, "message": "Генератор вернул пустой список задач."}

        tasks_list = _split_numbered(tasks_text_raw)
        tasks_items_tex = _items_to_latex(tasks_list)

        # 2) Решения (преподавателю)
        sgen = await generate_solutions_for_tasks(tasks_text_raw)
        solutions_text_raw = _cleanup_text(sgen.get("solutions_text", ""))

        solutions_items_tex = ""
        if solutions_text_raw:
            sol_list = _split_numbered(solutions_text_raw)
            solutions_items_tex = _items_to_latex(sol_list)

        # 3) Сборка двух PDF
        #   3.1 Только задачи
        student_latex = STUDENT_TPL.render(tasks_items=tasks_items_tex)
        tasks_pdf_b64, log1 = compile_latex_to_b64(student_latex, engine="xelatex")
        if not tasks_pdf_b64:
            logger.error("PDF Tasks compile error: %s", log1 or "compile failed")

        #   3.2 Задачи + решения
        teacher_latex = TEACHER_TPL.render(
            tasks_items=tasks_items_tex,
            solutions_items=solutions_items_tex
        )
        solutions_pdf_b64, log2 = compile_latex_to_b64(teacher_latex, engine="xelatex")
        if not solutions_pdf_b64:
            logger.error("PDF Solutions compile error: %s", log2 or "compile failed")

        # 4) Результат — совместимые поля
        result: Dict[str, Any] = {
            "type": "tasks",
            "task_id": task_id,
            "tasks_text": tasks_text_raw,
            "solutions_text": solutions_text_raw,
            "latex_tasks": student_latex,
            "latex_solutions": teacher_latex,
            "tasks_pdf_b64": tasks_pdf_b64 or "",
            "solutions_pdf_b64": solutions_pdf_b64 or "",
            # совместимость со старым кодом бота:
            "file": tasks_pdf_b64 or "",              # основной файл для ученика
            "solutions_file": solutions_pdf_b64 or "",# файл с решениями для преподавателя
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
