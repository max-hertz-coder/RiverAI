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

# XeLaTeX-дружественный шаблон с безопасными catcodes в теле
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

% Безопасные catcodes для спецсимволов в тексте:
{\catcode`\^=12\relax \catcode`\_=12\relax
{{ body | safe }}
}

\end{document}
"""
template_homework_check = Template(HOMEWORK_CHECK_TEMPLATE)


def clean_latex_for_check(text: str) -> str:
    """Лёгкая подчистка системного мусора от моделей."""
    return (text or "").replace("`", "")


async def check_homework(homework_text: str) -> Dict[str, Any]:
    """
    Основной вызов GPT для проверки ДЗ.
    Для скорости и качества используем gpt-4-turbo (как ты просил для «простых задач»).
    """
    system_prompt = (
        "Вы — опытный преподаватель математики. Проверьте домашнюю работу ниже, найдите ошибки и дайте комментарии.\n\n"
        "Оформите ответ в ПРОСТОМ LaTeX формате, используя ТОЛЬКО следующие команды:\n"
        "- \\section*{название}\n- \\begin{enumerate} ... \\end{enumerate}\n- \\item\n\n"
        "Важные правила:\n"
        "1) Каждый \\item с новой строки\n"
        "2) Без пустых enumerate\n"
        "3) Простые названия разделов по-русски\n"
        "4) Без \\textbf, \\textit и прочих оформлений\n"
        "5) Избегайте специальных Unicode-символов — используйте обычный текст\n"
        "6) Не используйте звёздочки (*) в названиях\n"
        "7) В тексте не используйте фигурные скобки кроме обязательных в командах\n"
        "Структура:\n"
        "\\section*{Общая оценка}\n...\n\n"
        "\\section*{Найденные ошибки}\n\\begin{enumerate}\n\\item ...\n\\end{enumerate}\n\n"
        "\\section*{Рекомендации}\n\\begin{enumerate}\n\\item ...\n\\end{enumerate}"
    )

    return await chat_with_gpt(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Проверьте эту домашнюю работу:\n\n{homework_text}"},
        ],
        temperature=0.2,
        max_tokens=4000,
        model="gpt-4-turbo",
    )


async def handle_homework_check(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Главный обработчик: готовит PDF (base64) с отчётом проверки.
    """
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

        # Нормализуем LaTeX-тело (без преамбулы) + лёгкая подчистка
        body = normalize_gpt_latex(check_raw)
        body = clean_latex_for_check(body)

        # Собираем документ и компилим XeLaTeX'ом
        latex_full = template_homework_check.render(body=body)
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


# === Опционально: сборка отчёта из структурированных полей ===

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
