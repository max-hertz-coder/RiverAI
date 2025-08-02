import logging
from worker.services.homework_check_service import handle_homework_check
from worker.services.pdf_utils import compile_latex_to_pdf

async def handle_check_homework(task: dict) -> dict:
    """
    Проверка домашнего задания — отправка текста на ревью с генерацией PDF.
    """
    task_id = task.get("task_id")
    text = task.get("text", "").strip()

    if not task_id:
        return {
            "type": "error",
            "message": "Отсутствует task_id."
        }

    if not text:
        return {
            "type": "error",
            "message": "❌ Не передан текст для проверки"
        }

    try:
        # Используем новый сервис для проверки ДЗ
        result = await handle_homework_check({
            "task_id": task_id,
            "text": text
        })
        
        if result.get("type") == "error":
            return result
        
        # Генерируем PDF отчет
        latex_content = result.get("latex_content", "")
        if latex_content:
            # Создаем LaTeX документ для проверки ДЗ
            latex_template = r"""\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\begin{document}

\begin{center}
\textbf{Результат проверки домашнего задания}
\end{center}

\vspace{1cm}

%s

\end{document}""" % latex_content
            
            pdf_path, log = compile_latex_to_pdf(latex_template)
            
            if pdf_path:
                return {
                    "type": "check",
                    "task_id": task_id,
                    "report_text": result.get("check_result", ""),
                    "pdf_path": pdf_path,
                    "original_text": text
                }
            else:
                # Если не удалось сгенерировать PDF, возвращаем только текст
                return {
                    "type": "check",
                    "task_id": task_id,
                    "report_text": result.get("check_result", ""),
                    "original_text": text
                }
        else:
            return {
                "type": "error",
                "message": "Не удалось получить результат проверки"
            }
            
    except Exception as e:
        logging.exception("Ошибка в check_homework")
        return {
            "type": "error",
            "message": f"Ошибка при проверке ДЗ: {e}"
        }