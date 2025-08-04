import os
import tempfile
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
from jinja2 import Template
import re

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

# Шаблон для проверки ДЗ
HOMEWORK_CHECK_TEMPLATE = r"""\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\begin{document}

\begin{center}
\textbf{Результат проверки домашнего задания}
\end{center}

\vspace{1cm}

{{ check_result }}

\end{document}
"""

template_homework_check = Template(HOMEWORK_CHECK_TEMPLATE)


async def check_homework(homework_text: str) -> str:
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

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Проверьте эту домашнюю работу:\n\n{homework_text}"}
            ],
            temperature=0.0,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("Ошибка при проверке ДЗ: %s", e)
        return f"❌ Не удалось проверить ДЗ: {str(e)}"


def clean_latex_for_check(text: str) -> str:
    """
    Очищает LaTeX код от потенциально проблемных символов.
    """
    # Удаляем только самые проблемные символы, но сохраняем структуру LaTeX
    text = text.replace('`', '')  # Удаляем обратные кавычки
    return text


def escape_latex(text: str) -> str:
    """
    Экранирует специальные символы для LaTeX, но сохраняет LaTeX команды.
    """
    # Экранируем только специальные символы, НЕ трогаем обратные слеши и фигурные скобки
    replacements = {
        '&': '\\&',
        '%': '\\%',
        '$': '\\$',
        '#': '\\#',
        '^': '\\^{}',
        '_': '\\_',
        '~': '\\~{}',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


async def handle_homework_check(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи проверки домашнего задания.
    Принимает task с полями: task_id, text (текст ДЗ)
    Возвращает результат проверки в LaTeX формате.
    """
    task_id = task.get("task_id")
    homework_text = task.get("text", "").strip()
    
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not homework_text:
        return {"type": "error", "message": "Нет текста для проверки."}
    
    try:
        # Проверяем ДЗ
        check_result = await check_homework(homework_text)
        logger.info(f"🔧 check_homework: получили результат, длина: {len(check_result)}")
        
        # Очищаем и экранируем результат
        cleaned_result = clean_latex_for_check(check_result)
        logger.info(f"🔧 check_homework: очистили результат, длина: {len(cleaned_result)}")
        
        escaped_result = escape_latex(cleaned_result)
        logger.info(f"🔧 check_homework: экранировали результат, длина: {len(escaped_result)}")
        logger.info(f"🔧 check_homework: первые 200 символов: {escaped_result[:200]}...")
        
        # Создаем LaTeX документ
        latex_content = template_homework_check.render(check_result=escaped_result)
        logger.info(f"🔧 check_homework: создали LaTeX документ, длина: {len(latex_content)}")
        
        return {
            "type": "homework_check",
            "task_id": task_id,
            "original_text": homework_text,
            "check_result": check_result,
            "latex_content": latex_content
        }
        
    except Exception as e:
        logger.exception("Ошибка в handle_homework_check: %s", e)
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при проверке ДЗ: {str(e)}"
        } 