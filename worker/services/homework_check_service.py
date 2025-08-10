# worker/services/homework_check_service.py
from __future__ import annotations

import base64
import json
import logging
from typing import Dict, Any, List
from jinja2 import Template

from worker.services.gpt_service import chat_with_gpt
from worker.services.pdf_utils import (
    normalize_gpt_latex,
    compile_latex_to_b64,  # путь 1: компиляция ответа GPT (готовый LaTeX body)
    # Ниже — для альтернативного пути сборки отчёта из структурированных секций:
    escape_text,
    build_document,
    compile_latex,  # возвращает bytes | None
)

logger = logging.getLogger(__name__)

# ====== Шаблон итогового отчёта для варианта с «сырым» LaTeX от GPT ======
HOMEWORK_CHECK_TEMPLATE = r"""
\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amsfonts,amssymb}
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
    """Простая чистка от случайных символов, если потребуется."""
    return (text or "").replace("`", "")


def escape_latex_text(text: str) -> str:
    """Упрощённое экранирование (если когда-то понадобится для plain-текста)."""
    repl = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "^": r"\^{}", "_": r"\_", "~": r"\~{}"}
    out = text or ""
    for a, b in repl.items():
        out = out.replace(a, b)
    return out


async def check_homework(homework_text: str) -> Dict[str, Any]:
    """
    Запрашивает у GPT проверку ДЗ и возвращает ответ модели.
    ВАЖНО: system_prompt оставлен БЕЗ ИЗМЕНЕНИЙ.
    """
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

    resp = await chat_with_gpt(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Проверьте эту домашнюю работу:\n\n{homework_text}"},
        ],
        temperature=0.0,
        max_tokens=4000,
    )
    return resp


async def handle_homework_check(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Основной обработчик задачи: берём текст ДЗ, просим GPT выдать LaTeX-тело,
    заворачиваем в наш документ и компилируем PDF на воркере.
    Возвращаем:
      {
        "type": "homework_check",
        "task_id": ...,
        "original_text": "...",
        "check_result": "<сырой LaTeX-ответ GPT, до нормализации>",
        "file": "<base64 pdf>" | None,
        "prompt_tokens": int,
        "completion_tokens": int,
        "latex_content": "<полный .tex>",  # для отладки
      }
    """
    task_id = task.get("task_id")
    homework_text = (task.get("text") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    if not homework_text:
        return {"type": "error", "task_id": task_id, "message": "Нет текста для проверки."}

    try:
        resp = await check_homework(homework_text)

        # Сырый текст (ожидаем LaTeX-тело секций)
        check_raw = (resp.get("text") or resp.get("content") or "").strip()
        logger.info("🔧 check_homework: длина ответа = %d", len(check_raw))

        # Нормализуем LaTeX-тело (убираем \documentclass...\begin{document} если вдруг пришло)
        body = normalize_gpt_latex(check_raw)
        body = clean_latex_for_check(body)

        # Собираем полный документ через шаблон
        latex_full = template_homework_check.render(body=body)

        # Компилируем на воркере (pdflatex/xelatex — внутри pdf_utils)
        file_b64, log = compile_latex_to_b64(latex_full)
        if not file_b64:
            logger.error("Homework PDF compile error: %s", (log or "")[:1200])

        return {
            "type": "homework_check",
            "task_id": task_id,
            "original_text": homework_text,
            "check_result": check_raw,  # для подписи рядом с PDF (или на случай фолбэка)
            "file": file_b64,           # может быть None при ошибке компиляции
            "prompt_tokens": int(resp.get("prompt_tokens", 0)),
            "completion_tokens": int(resp.get("completion_tokens", 0)),
            "latex_content": latex_full,
        }

    except Exception as e:
        logger.exception("Ошибка в handle_homework_check")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка при проверке ДЗ: {e}"}


# ====== Альтернативный путь: сборка отчёта из структурированных полей ======
# Используется, если где-то в пайплайне уже получен разобранный JSON с полями
# overview / errors[] / recommendations[] и нужно собрать такой же PDF.
def _render_report(overview: str, errors: List[str], recs: List[str]) -> str:
    """Готовим LaTeX-тело отчёта (три секции)."""
    body_parts: List[str] = []

    if overview:
        body_parts.append("\\section*{Общая оценка}\n" + escape_text(overview))

    if errors:
        body_parts.append("\\section*{Найденные ошибки}\n\\begin{enumerate}")
        for it in errors:
            body_parts.append("\\item " + escape_text(it))
        body_parts.append("\\end{enumerate}")

    if recs:
        body_parts.append("\\section*{Рекомендации}\n\\begin{enumerate}")
        for it in recs:
            body_parts.append("\\item " + escape_text(it))
        body_parts.append("\\end{enumerate}")

    return "\n\n".join(body_parts)


async def build_pdf_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    На вход: словарь с ключами:
      - overview: str
      - errors: List[str]
      - recommendations: List[str]
      - fallback_text: str (что показать текстом, если PDF не собрался)
    На выход: { type:'homework_check', check_result: str, file?: base64, latex_content: str }
    """
    overview = (payload.get("overview") or "").strip()
    errors = payload.get("errors") or []
    recs = payload.get("recommendations") or []
    fallback_text = (payload.get("fallback_text") or "").strip()

    latex_body = _render_report(overview, errors, recs)
    tex = build_document("Результат проверки ДЗ", latex_body)
    pdf_bytes = compile_latex(tex)  # bytes | None

    # короткий текст (для подписи в чате)
    blocks: List[str] = []
    if overview:
        blocks.append(f"Общая оценка:\n{overview}")
    if errors:
        bullets = "\n".join(f"• {e}" for e in errors)
        blocks.append(f"Найденные ошибки:\n{bullets}")
    if recs:
        bullets = "\n".join(f"• {r}" for r in recs)
        blocks.append(f"Рекомендации:\n{bullets}")
    short_text = "\n\n".join(blocks) or fallback_text or "Отчёт сформирован."

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
