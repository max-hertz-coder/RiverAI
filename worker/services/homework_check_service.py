# worker/services/homework_check_service.py
from __future__ import annotations

import base64
import logging
from typing import Dict, Any, List
from jinja2 import Template

from worker.services.gpt_service import chat_with_gpt
from worker.services.pdf_utils import (
    normalize_gpt_latex,
    compile_latex_to_b64,  # поддерживает engine=
    escape_text,
    build_document,
    compile_latex,
)

logger = logging.getLogger(__name__)

# Шаблон отчёта под XeLaTeX (unicode-safe)
HOMEWORK_CHECK_TEMPLATE = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\setlist{noitemsep, topsep=2pt}
\begin{document}
\begin{center}
\textbf{Результат проверки домашнего задания}
\end{center}
\vspace{0.5cm}
{{ body | safe }}
\end{document}
"""
template_homework_check = Template(HOMEWORK_CHECK_TEMPLATE)


def clean_latex_for_check(text: str) -> str:
    # лёгкая подчистка «косых» кавычек/тильд и т.п. (если нужно — можно расширить)
    return (text or "").replace("`", "")


async def check_homework(homework_text: str) -> Dict[str, Any]:
    # ВАЖНО: system_prompt не меняю.
    system_prompt = """Вы — опытный преподаватель математики. Проверьте домашнюю работу ниже, найдите ошибки и дайте комментарии.

        Оформите ответ в ПРОСТОМ LaTeX формате, используя ТОЛЬКО следующие команды:
        - \\section*{название} - для разделов
        - \\begin{enumerate} ... \\end{enumerate} - для списков
        - \\item - для элементов списка

        ВАЖНЫЕ ПРАВИЛА:
        1. Каждый \\item должен быть на отдельной строке
        2. Не оставляйте пустые enumerate блоки
        3. Используйте простые названия разделов на русском языке
        4. НЕ используйте \\textbf, \\textit или другие команды форматирования
        5. НЕ используйте Unicode символы вообще
        6. НЕ используйте математические символы в тексте
        7. Пишите простым текстом без специальных символов
        8. НЕ используйте звездочки (*) в названиях разделов
        9. Используйте только кириллицу в названиях разделов
        10. НЕ используйте фигурные скобки в тексте, только в командах
        11. Избегайте сложных конструкций

        Структура ответа:
        \\section*{Общая оценка}
        [Краткая общая оценка работы]

        \\section*{Найденные ошибки}
        \\begin{enumerate}
        \\item [Описание ошибки 1]
        \\item [Описание ошибки 2]
        \\end{enumerate}

        \\section*{Рекомендации}
        \\begin{enumerate}
        \\item [Рекомендация 1]
        \\item [Рекомендация 2]
        \\end{enumerate}"""

    return await chat_with_gpt(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Проверьте эту домашнюю работу:\n\n{homework_text}"},
        ],
        temperature=0.0,
        max_tokens=4000,
    )


async def handle_homework_check(task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = task.get("task_id")
    homework_text = (task.get("text") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    if not homework_text:
        return {"type": "error", "task_id": task_id, "message": "Нет текста для проверки."}

    try:
        resp = await check_homework(homework_text)
        check_raw = (resp.get("text") or resp.get("content") or "").strip()
        logger.info("🔧 check_homework: длина ответа = %d", len(check_raw))

        # 1) нормализуем «тело» LaTeX (убираем лишнюю преамбулу, приводим кавычки/тире и т.д.)
        body = normalize_gpt_latex(check_raw)
        body = clean_latex_for_check(body)

        # 2) собираем полноценный документ (XeLaTeX-дружелюбный)
        latex_full = template_homework_check.render(body=body)

        # 3) компилим XeLaTeX'ом
        file_b64, log = compile_latex_to_b64(latex_full, engine="xelatex")
        if not file_b64:
            logger.error("Homework PDF compile error: %s", (log or "compile failed"))

        return {
            "type": "homework_check",
            "task_id": task_id,
            "original_text": homework_text,
            "check_result": check_raw,
            "file": file_b64,  # base64 PDF или None
            "prompt_tokens": int(resp.get("prompt_tokens", 0)),
            "completion_tokens": int(resp.get("completion_tokens", 0)),
            "latex_content": latex_full,
        }

    except Exception as e:
        logger.exception("Ошибка в handle_homework_check")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка при проверке ДЗ: {e}"}


# === Доп. путь: сборка отчёта из структурированных полей ===

def _render_report(overview: str, errors: List[str], recs: List[str]) -> str:
    parts: List[str] = []
    if overview:
        parts.append("\\section*{Общая оценка}\n" + escape_text(overview))
    if errors:
        parts.append("\\section*{Найденные ошибки}\n\\begin{enumerate}")
        parts += ["\\item " + escape_text(e) for e in errors]
        parts.append("\\end{enumerate}")
    if recs:
        parts.append("\\section*{Рекомендации}\n\\begin{enumerate}")
        parts += ["\\item " + escape_text(r) for r in recs]
        parts.append("\\end{enumerate}")
    return "\n\n".join(parts)


async def build_pdf_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    overview = (payload.get("overview") or "").strip()
    errors = payload.get("errors") or []
    recs = payload.get("recommendations") or []
    fallback_text = (payload.get("fallback_text") or "").strip()

    body = _render_report(overview, errors, recs)
    tex = build_document("Результат проверки ДЗ", body)

    pdf_bytes = compile_latex(tex, engine="xelatex")
    short_text_parts: List[str] = []
    if overview:
        short_text_parts.append(f"Общая оценка:\n{overview}")
    if errors:
        short_text_parts.append("Найденные ошибки:\n" + "\n".join(f"• {e}" for e in errors))
    if recs:
        short_text_parts.append("Рекомендации:\n" + "\n".join(f"• {r}" for r in recs))
    short_text = "\n\n".join(short_text_parts) or fallback_text or "Отчёт сформирован."

    result: Dict[str, Any] = {
        "type": "homework_check",
        "check_result": short_text,
        "latex_content": tex,
    }
    if pdf_bytes:
        result["file"] = base64.b64encode(pdf_bytes).decode("ascii")
    else:
        logger.error("Homework PDF compile failed; sending text only")
    return result
