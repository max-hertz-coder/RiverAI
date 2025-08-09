# worker/services/pdf_utils.py
"""
Утилиты для подготовки и безопасной компиляции LaTeX на ВОРКЕРЕ:
- template_basic / template_solutions — Jinja2-шаблоны
- escape_latex / sanitize_solutions — предобработка текста
- compile_latex_to_pdf_bytes / compile_latex_to_b64 — компиляция через pdflatex
"""
import base64
import tempfile
import subprocess
import re
from pathlib import Path
from typing import List, Tuple, Optional

from jinja2 import Template

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


def compile_latex_to_pdf_bytes(latex: str, timeout: int = 40) -> Tuple[Optional[bytes], str]:
    """
    Компилирует LaTeX-строку в PDF и возвращает (pdf_bytes | None, log_text).
    Делаем две прогонки pdflatex для устойчивости.
    """
    try:
        with tempfile.TemporaryDirectory() as td:
            tex = Path(td) / "out.tex"
            pdf = Path(td) / "out.pdf"
            tex.write_text(latex or "", encoding="utf-8")

            logs: List[str] = []
            for _ in range(2):
                proc = subprocess.run(
                    ["pdflatex", "-halt-on-error", "-interaction=nonstopmode", tex.name],
                    cwd=td,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                logs.append(proc.stdout.decode("utf-8", errors="ignore"))
                if proc.returncode != 0:
                    break

            if not pdf.exists():
                return None, "\n\n".join(logs)

            return pdf.read_bytes(), ""
    except FileNotFoundError:
        return None, "pdflatex not found in PATH"
    except Exception as e:
        return None, str(e)


def compile_latex_to_b64(latex: str, timeout: int = 40) -> Tuple[Optional[str], str]:
    """
    Обертка над compile_latex_to_pdf_bytes: возвращает (base64 | None, log).
    """
    pdf_bytes, log = compile_latex_to_pdf_bytes(latex, timeout=timeout)
    if not pdf_bytes:
        return None, log
    return base64.b64encode(pdf_bytes).decode("utf-8"), ""


def sanitize_solutions(sols_list: List[str]) -> List[str]:
    """
    Убирает оболочки itemize и \item, возвращает «чистый» текст решения.
    """
    sanitized: List[str] = []
    for sol in sols_list:
        clean = re.sub(r'\\begin\{itemize\}|\\end\{itemize\}', '', sol or '')
        clean = re.sub(r'\\item\s*', '', clean)
        sanitized.append(clean.strip())
    return sanitized


def escape_latex(text: str) -> str:
    """
    Экранирует спецсимволы за пределами math-режимов.
    Math-режимы ($...$, $$...$$, \[...\], \(...\)) оставляем как есть.
    """
    math_pat = re.compile(r'(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\))', flags=re.DOTALL)
    parts = math_pat.split(text or "")
    safe: List[str] = []

    for part in parts:
        if math_pat.fullmatch(part or ""):
            safe.append(part)
        else:
            part = (part or "").replace('\\', r'\textbackslash{}')
            for ch, esc in {
                '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_',
                '{': r'\{', '}': r'\}', '~': r'\~{}', '^': r'\^{}',
            }.items():
                part = part.replace(ch, esc)
            safe.append(part)

    return ''.join(safe)
