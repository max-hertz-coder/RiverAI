import tempfile
import subprocess
import logging
from pathlib import Path
import base64
from jinja2 import Template
from aiogram.types import BufferedInputFile

from bot_app import config
from common.redis_utils import save_last_solutions_file

# ——— Шаблоны LaTeX (в синхроне с worker/pdf_utils) ———
BASIC_TEMPLATE = r"""\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amsfonts,amssymb}
\begin{document}
\begin{center}{\LARGE\bfseries {{ title }}} \end{center}
\section*{Задачи}
\begin{enumerate}
{{ content }}
\end{enumerate}
\end{document}
"""

SOLUTIONS_TEMPLATE = r"""\documentclass[12pt]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amsfonts,amssymb}
\begin{document}
\begin{center}{\LARGE\bfseries Решения} \end{center}
\section*{Задачи}
\begin{enumerate}
{{ content_tasks }}
\end{enumerate}
\section*{Решения}
\begin{enumerate}
{{ content_solutions }}
\end{enumerate}
\end{document}
"""

template_basic = Template(BASIC_TEMPLATE)
template_solutions = Template(SOLUTIONS_TEMPLATE)


def compile_latex_to_pdf(latex: str) -> tuple[str | None, str]:
    """
    Компилирует LaTeX в PDF используя pdflatex.
    Возвращает (путь_к_pdf | None, log).
    """
    try:
        with tempfile.TemporaryDirectory() as td:
            tex = Path(td) / "out.tex"
            pdf = Path(td) / "out.pdf"
            tex.write_text(latex or "", encoding="utf-8")

            proc = subprocess.run(
                ["pdflatex", "-halt-on-error", "-interaction=nonstopmode", tex.name],
                cwd=td,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=25,
            )
            log = proc.stdout.decode("utf-8", errors="ignore")

            if proc.returncode != 0 or not pdf.exists():
                return None, log

            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            out.write(pdf.read_bytes())
            out.flush()
            return out.name, ""
    except FileNotFoundError:
        return None, "pdflatex not found in PATH"
    except Exception as e:
        logging.exception("Ошибка компиляции LaTeX: %s", e)
        return None, str(e)


async def compile_and_send_pdfs(latex_tasks: str, latex_solutions: str, bot, user_id: int) -> dict:
    """
    Компилирует LaTeX → отправляет пользователю два PDF → сохраняет Solutions в Redis (base64).
    Возвращает словарь путей: {"tasks": path|None, "solutions": path|None}.
    """
    result_paths = {"tasks": None, "solutions": None}
    try:
        # Tasks
        pdf_t_path, log_t = compile_latex_to_pdf(latex_tasks)
        if pdf_t_path:
            result_paths["tasks"] = pdf_t_path
            with open(pdf_t_path, "rb") as f:
                document = BufferedInputFile(f.read(), filename="Tasks.pdf")
            await bot.send_document(user_id, document, caption="📎 PDF: Задания")
            logging.info("✅ PDF Tasks отправлен пользователю %s", user_id)
        else:
            logging.error("🔴 Ошибка компиляции PDF Tasks: %s", log_t)
            await bot.send_message(user_id, "❌ Ошибка создания PDF с заданиями")

        # Solutions
        pdf_s_path, log_s = compile_latex_to_pdf(latex_solutions)
        if pdf_s_path:
            result_paths["solutions"] = pdf_s_path
            with open(pdf_s_path, "rb") as f:
                file_bytes = f.read()
            await bot.send_document(user_id, BufferedInputFile(file_bytes, filename="Solutions.pdf"),
                                    caption="📎 PDF: Решения")
            # сохраняем Solutions.pdf в Redis для режима «✏️ Переделать»
            await save_last_solutions_file(user_id, base64.b64encode(file_bytes).decode())
            logging.info("✅ PDF Solutions отправлен пользователю %s", user_id)
        else:
            logging.error("🔴 Ошибка компиляции PDF Solutions: %s", log_s)
            await bot.send_message(user_id, "❌ Ошибка создания PDF с решениями")

    except Exception as e:
        logging.exception("🔴 Ошибка отправки PDF: %s", e)
        try:
            await bot.send_message(config.ADMIN_CHAT_ID,
                                   f"🔴 Ошибка отправки PDF пользователю {user_id}:\n{e}")
        except Exception:
            logging.exception("Не удалось уведомить админа об ошибке PDF")

    return result_paths
