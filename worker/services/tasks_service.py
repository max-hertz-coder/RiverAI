# worker/services/tasks_service.py

from worker.tasks import generate_tasks
import logging
import base64

logger = logging.getLogger(__name__)

LATEX_TEMPLATE = r"""
\documentclass[12pt]{article}
\usepackage{fontspec}
\usepackage{polyglossia}
\setmainlanguage{russian}
\newfontfamily\cyrillicfont{FreeSerif}
\setmainfont{FreeSerif}
\usepackage{amsmath}
\usepackage{geometry}
\geometry{margin=2cm}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection.}{1em}{}

\begin{document}

\section*{Сгенерированные задания}

%TASKS%

\end{document}
"""

async def handle_tasks(task: dict) -> dict:
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    task_type = task.get("type")

    try:
        result = await generate_tasks.execute(task)
        latex_body = result.get("corrected_tasks") or result.get("raw_tasks")
        if not latex_body:
            return {
                "type": "error",
                "user_id": user_id,
                "message": "Не удалось сгенерировать задачи. Ответ пуст."
            }

        latex_full = LATEX_TEMPLATE.replace("%TASKS%", latex_body)

        from worker.services.latex_service import compile_latex_to_pdf
        pdf_bytes = await compile_latex_to_pdf(latex_full)

        file_url = None
        file_b64 = None

        from worker import db
        from worker.utils import encryption
        from worker.services import storage_service

        user = await db.get_user(user_id)
        if user and user.get("ydisk_token_enc"):
            token = encryption.decrypt_str(user["ydisk_token_enc"])
            from datetime import datetime
            dt = datetime.now().strftime("%Y-%m-%d_%H-%M")
            filename = f"Задания_{student_id}_{dt}.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_bytes, filename)
            if success:
                file_url = "yadisk"

        if not file_url and pdf_bytes:
            file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return {
            "type": "tasks",
            "user_id": user_id,
            "student_id": student_id,
            "file": file_b64,
            "file_url": file_url
        }

    except Exception:
        logger.exception("🔴 Ошибка при генерации заданий")
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Ошибка при генерации задания."
        }
