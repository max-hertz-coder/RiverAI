import logging
from typing import Dict, Any
from jinja2 import Template

from worker.services.gpt_service import chat_with_gpt
from worker.services.pdf_utils import compile_latex_to_b64

logger = logging.getLogger(__name__)

# Лёгкий шаблон для отчёта
HOMEWORK_CHECK_TEMPLATE = r"""
\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\begin{document}
\begin{center}
\textbf{Результат проверки домашнего задания}
\end{center}
\vspace{0.5cm}
{{ check_result }}
\end{document}
"""

template_homework_check = Template(HOMEWORK_CHECK_TEMPLATE)


def clean_latex_for_check(text: str) -> str:
    return (text or "").replace("`", "")


def escape_latex_text(text: str) -> str:
    repl = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "^": r"\^{}", "_": r"\_", "~": r"\~{}"}
    out = text or ""
    for a, b in repl.items():
        out = out.replace(a, b)
    return out

async def check_homework(homework_text: str) -> Dict[str, Any]:
    """
    Проверяет домашнее задание с помощью GPT и возвращает анализ в LaTeX формате.
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
    task_id = task.get("task_id")
    homework_text = (task.get("text") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    if not homework_text:
        return {"type": "error", "task_id": task_id, "message": "Нет текста для проверки."}

    try:
        resp = await check_homework(homework_text)
        check_result = (resp.get("text") or "").strip()
        logger.info("🔧 check_homework: длина ответа = %d", len(check_result))

        cleaned = clean_latex_for_check(check_result)
        escaped = escape_latex_text(cleaned)

        latex_content = template_homework_check.render(check_result=escaped)

        # КОМПИЛИРУЕМ НА ВОРКЕРЕ → base64
        file_b64, log = compile_latex_to_b64(latex_content)
        if not file_b64:
            logger.error("Homework PDF compile error: %s", (log or "")[:500])

        return {
            "type": "homework_check",
            "task_id": task_id,
            "original_text": homework_text,
            "check_result": check_result,
            "file": file_b64,  # ⟵ бот отправит этот PDF
            "prompt_tokens": int(resp.get("prompt_tokens", 0)),
            "completion_tokens": int(resp.get("completion_tokens", 0)),
        }

    except Exception as e:
        logger.exception("Ошибка в handle_homework_check")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка при проверке ДЗ: {e}"}