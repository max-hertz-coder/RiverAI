# worker/services/pdf_utils.py

import tempfile
import subprocess
import re
from pathlib import Path
from jinja2 import Template
from typing import List

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
template_basic     = Template(BASIC_TEMPLATE)
template_solutions = Template(SOLUTIONS_TEMPLATE)

def compile_latex_to_pdf(latex: str) -> tuple[str | None, str]:
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "out.tex"
        pdf = Path(td) / "out.pdf"
        tex.write_text(latex, encoding="utf-8")
        
        # Используем pdflatex для поддержки кириллицы
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

def sanitize_solutions(sols_list: List[str]) -> List[str]:
    """
    Убирает из каждого элемента списка любых оболочек itemize и сами команды \item,
    возвращая «чистый» текст решения, который потом упакуем в \\item.
    """
    sanitized = []
    for sol in sols_list:
        # 1) удаляем \begin{itemize} и \end{itemize}
        clean = re.sub(r'\\begin\{itemize\}|\\end\{itemize\}', '', sol)
        # 2) удаляем все \item и возможные пробелы после
        clean = re.sub(r'\\item\s*', '', clean)
        # 3) обрезаем по краям пробелы и пустые строки
        clean = clean.strip()
        sanitized.append(clean)
    return sanitized

def escape_latex(text: str) -> str:
    # Паттерн для math-режимов: $…$, $$…$$, \[…\], \(…\)
    math_pat = re.compile(
        r'(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\))',
        flags=re.DOTALL
    )
    parts = math_pat.split(text)
    safe = []
    for part in parts:
        if math_pat.fullmatch(part):
            # оставляем math-режим нетронутым
            safe.append(part)
        else:
            # экранируем всё, что может сломать TeX
            part = part.replace('\\', r'\textbackslash{}')
            for ch, esc in {
                '&': r'\&', '%': r'\%', '$': r'\$',
                '#': r'\#', '_': r'\_', '{': r'\{',
                '}': r'\}', '~': r'\~{}', '^': r'\^{}',
            }.items():
                part = part.replace(ch, esc)
            safe.append(part)
    return ''.join(safe)