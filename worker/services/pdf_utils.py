# worker/services/pdf_utils.py
"""
Утилиты для LaTeX на воркере:
- normalize_gpt_latex: вырезает преамбулу/\\begin{document}... и нормализует юникод
- escape_text / escape_latex: экранирование спецсимволов вне math
- sanitize_solutions: делает текст решений безопасным для LaTeX
- Jinja-шаблоны: template_basic, template_solutions
- build_document: собрать простой документ
- компиляция: compile_latex / compile_latex_to_b64 / compile_latex_to_pdf_bytes
"""

from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional

from jinja2 import Template

# ---------- Нормализация сырого LaTeX (если приходит из GPT) ----------
_STRIP_DOC_RE = re.compile(r"\\documentclass[\s\S]*?\\begin\{document\}", re.IGNORECASE)
_END_DOC_RE = re.compile(r"\\end\{document\}\s*$", re.IGNORECASE)

def normalize_gpt_latex(s: str) -> str:
    if not s:
        return ""
    s = _STRIP_DOC_RE.sub("", s)
    s = _END_DOC_RE.sub("", s)

    repl = {
        "\u00A0": " ",
        "–": "--",
        "—": "---",
        "“": "«", "”": "»",
        "„": "«", "‟": "»",
        "’": "'", "‘": "'",
        "…": "...",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.strip()

# ---------- Экранирование обычного текста ----------
_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_math_re = re.compile(r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\))", re.DOTALL)

def escape_text(s: str) -> str:
    """Экранируем спецсимволы вне math-режимов."""
    if not s:
        return ""
    parts: List[str] = []
    idx = 0
    for m in _math_re.finditer(s):
        chunk = s[idx:m.start()]
        parts.append("".join(_LATEX_SPECIALS.get(ch, ch) for ch in chunk))
        parts.append(m.group(0))  # math — как есть
        idx = m.end()
    tail = s[idx:]
    parts.append("".join(_LATEX_SPECIALS.get(ch, ch) for ch in tail))
    return "".join(parts)

# совместимость с существующим кодом
def escape_latex(s: str) -> str:
    return escape_text(s)

# ---------- Санитизация решений ----------
_GREEK_MAP = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta",
    "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu",
    "ν": "nu", "ξ": "xi", "ο": "o", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi",
    "χ": "chi", "ψ": "psi", "ω": "omega",
    "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi",
    "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}

_UNICODE_SYM_REPL = {
    "≤": "<=", "≥": ">=", "≠": "!=",
    "≈": "~", "×": "x", "·": "*", "•": "*",
    "√": "sqrt", "∞": "infty",
    "→": "->", "←": "<-",
}

def _replace_unicode_math(text: str) -> str:
    for u, r in _UNICODE_SYM_REPL.items():
        text = text.replace(u, r)
    # греческие → латиницей
    def _sub_greek(m: re.Match) -> str:
        ch = m.group(0)
        return _GREEK_MAP.get(ch, ch)
    return re.sub("|".join(map(re.escape, _GREEK_MAP.keys())), _sub_greek, text)

def sanitize_solutions(items: List[str]) -> List[str]:
    """Приводим решения к безопасному для LaTeX тексту."""
    out: List[str] = []
    for s in items or []:
        s = s or ""
        # прибираем «заборы» кода ```…```
        if s.strip().startswith("```") and s.strip().endswith("```"):
            s = s.strip("`\n")
        # унификация юникода
        s = _replace_unicode_math(s)
        # удалим «сырой» backtick, BOM и прочий мусор
        s = s.replace("`", "").replace("\ufeff", "")
        # финальное экранирование
        s = escape_text(s)
        out.append(s)
    return out

# ---------- Jinja-шаблоны (XeLaTeX) ----------
LATEX_PREAMBLE_XE = r"""
\documentclass[12pt,a4paper]{article}
\usepackage{geometry}
\geometry{margin=2cm}
\usepackage{fontspec}
\usepackage{polyglossia}
\setmainlanguage{russian}
\setmainfont{DejaVu Serif}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{enumitem}
\setlist{nosep}
\usepackage{hyperref}
"""

_TEMPLATE_BASIC = LATEX_PREAMBLE_XE + r"""
\title{ {{ title|e }} }
\date{}
\begin{document}
\maketitle
\begin{enumerate}
{{ content | safe }}
\end{enumerate}
\end{document}
"""

_TEMPLATE_SOLUTIONS = LATEX_PREAMBLE_XE + r"""
\title{ Задачи и решения }
\date{}
\begin{document}
\maketitle

\section*{Задачи}
\begin{enumerate}
{{ content_tasks | safe }}
\end{enumerate}

\section*{Решения}
\begin{enumerate}
{{ content_solutions | safe }}
\end{enumerate}

\end{document}
"""

template_basic = Template(_TEMPLATE_BASIC)
template_solutions = Template(_TEMPLATE_SOLUTIONS)

def build_document(title: str, body: str) -> str:
    return (LATEX_PREAMBLE_XE + r"""
\title{ """ + (escape_text(title or "Отчёт")) + r""" }
\date{}
\begin{document}
\maketitle
""" + (body or "") + r"""
\end{document}
""")

# ---------- Компиляция ----------
def _compile(tex: str, engine: str = "xelatex", timeout: int = 120) -> Tuple[Optional[bytes], Optional[str]]:
    engine = engine or "xelatex"
    cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        (tmp / "main.tex").write_text(tex, encoding="utf-8")
        try:
            for _ in range(2):
                proc = subprocess.run(
                    cmd, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
                )
                if proc.returncode != 0:
                    return None, proc.stdout
            pdf_path = tmp / "main.pdf"
            if not pdf_path.exists():
                return None, "no pdf produced"
            return pdf_path.read_bytes(), None
        except Exception as e:
            return None, str(e)

def compile_latex(tex: str, engine: str = "xelatex", timeout: int = 120) -> Optional[bytes]:
    pdf, _ = _compile(tex, engine=engine, timeout=timeout)
    return pdf

def compile_latex_to_b64(tex: str, engine: str = "xelatex", timeout: int = 120) -> Tuple[Optional[str], Optional[str]]:
    pdf, log = _compile(tex, engine=engine, timeout=timeout)
    if not pdf:
        return None, log
    return base64.b64encode(pdf).decode("ascii"), None

# совместимость со старым кодом
def compile_latex_to_pdf_bytes(latex: str, timeout: int = 120) -> Tuple[Optional[bytes], str]:
    pdf, log = _compile(latex, engine="xelatex", timeout=timeout)
    return pdf, (log or "")
