import tempfile
import subprocess
import logging
from pathlib import Path
from jinja2 import Template

# Шаблоны LaTeX (те же, что и в worker)
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
    """Компилирует LaTeX код в PDF"""
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "out.tex"
        pdf = Path(td) / "out.pdf"
        tex.write_text(latex, encoding="utf-8")
        
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex.name],
            cwd=td,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20
        )
        log = proc.stdout.decode("utf-8", errors="ignore")
        
        if proc.returncode != 0 or not pdf.exists():
            return None, log
        
        out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        out.write(pdf.read_bytes())
        out.flush()
        return out.name, ""

def compile_and_send_pdfs(latex_tasks: str, latex_solutions: str, bot, user_id: int):
    """Компилирует LaTeX в PDF и отправляет пользователю"""
    try:
        # Компилируем PDF с задачами
        pdf_t_path, log_t = compile_latex_to_pdf(latex_tasks)
        if pdf_t_path:
            with open(pdf_t_path, "rb") as f:
                from io import BytesIO
                file_obj = BytesIO(f.read())
                file_obj.name = "Tasks.pdf"
                await bot.send_document(user_id, file_obj, caption="📎 PDF: Задания")
            logging.info(f"✅ PDF Tasks отправлен пользователю {user_id}")
        else:
            logging.error(f"🔴 Ошибка компиляции PDF Tasks: {log_t}")
            await bot.send_message(user_id, "❌ Ошибка создания PDF с заданиями")

        # Компилируем PDF с решениями
        pdf_s_path, log_s = compile_latex_to_pdf(latex_solutions)
        if pdf_s_path:
            with open(pdf_s_path, "rb") as f:
                from io import BytesIO
                file_obj = BytesIO(f.read())
                file_obj.name = "Solutions.pdf"
                await bot.send_document(user_id, file_obj, caption="📎 PDF: Решения")
            logging.info(f"✅ PDF Solutions отправлен пользователю {user_id}")
        else:
            logging.error(f"🔴 Ошибка компиляции PDF Solutions: {log_s}")
            await bot.send_message(user_id, "❌ Ошибка создания PDF с решениями")

    except Exception as e:
        logging.exception(f"🔴 Ошибка отправки PDF: {e}")
        await bot.send_message(user_id, f"❌ Ошибка отправки PDF: {e}") 