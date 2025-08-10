# worker/services/pdf_utils.py
"""
Утилиты для LaTeX на воркере:
- normalize_gpt_latex (если нужно чистить сырой LaTeX)
- escape_text: экранирование текста (не трогаем math-блоки $...$)
- build_document: простая преамбула + body
- compile_latex: сборка в PDF (две прогонки pdflatex; при неудаче — xelatex)
- compile_latex_to_b64 / compile_latex_to_pdf_bytes — совместимость со старым кодом
"""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional


# ---------- Нормализация сырого LaTeX (если приходит из GPT) ----------

_STRIP_DOC_RE = re.compile(r"\\documentclass[\s\S]*?\\begin\{document\}", flags=re.IGNORECASE)
_END_DOC_RE = re.compile(r"\\end\{document\}\s*$", flags=re.IGNORECASE)

def normalize_gpt_latex(s: str) -> str:
    if not s:
        return ""
    s = _STRIP_DOC_RE.sub("", s)
    s = _END_DOC_RE.sub("", s)
    # упрощённая нормализация unicode
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
    """
    Экранируем спецсимволы вне math-режимов ($...$, $$...$$, \[...\], \(...\)).
    """
    if not s:
        return ""
    parts: List[str] = []
    idx = 0
    for m in _math_re.finditer(s):
        chunk = s[idx:m.start()]
        parts.append("".join(_LATEX_SPECIALS.get(ch, ch) for ch in chunk))
        parts.append(m.group(0))  # math как есть
        idx = m.end()
    tail = s[idx:]
    parts.append("".join(_LATEX_SPECIALS.get(ch, ch) for ch in tail))
    return "".join(parts)


# ---------- Шаблон документа ----------

LATEX_TEMPLATE = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[russian]{babel}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{enumitem}
\usepackage{geometry}
\geometry{margin=2cm}
\usepackage{hyperref}
\setlist{nosep}

\title{%s}
\date{}

\begin{document}
\maketitle
%s
\end{document}
"""

def build_document(title: str, body: str) -> str:
    return LATEX_TEMPLATE % (escape_text(title or "Отчёт"), body or "")


# ---------- Компиляция ----------

def _run(cmd: List[str], cwd: str, timeout: int) -> Tuple[int, str]:
    p = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout
    )
    return p.returncode, p.stdout.decode("utf-8", errors="ignore")


# worker/services/pdf_utils.py — кусок с компиляцией

import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

def _compile(tex: str, engine: str = "xelatex") -> Tuple[Optional[bytes], Optional[str]]:
    """Компилирует LaTeX в PDF и возвращает (pdf_bytes | None, log | None)."""
    engine = engine or "xelatex"
    cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        (tmp / "main.tex").write_text(tex, encoding="utf-8")

        try:
            # два прогона, как обычно
            for _ in range(2):
                proc = subprocess.run(
                    cmd, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
                )
                if proc.returncode != 0:
                    return None, proc.stdout
            pdf_path = tmp / "main.pdf"
            if not pdf_path.exists():
                return None, "no pdf produced"
            return pdf_path.read_bytes(), None
        except Exception as e:
            return None, str(e)

def compile_latex(tex: str, engine: str = "xelatex") -> Optional[bytes]:
    pdf, _ = _compile(tex, engine=engine)
    return pdf

def compile_latex_to_b64(tex: str, engine: str = "xelatex") -> Tuple[Optional[str], Optional[str]]:
    pdf, log = _compile(tex, engine=engine)
    if not pdf:
        return None, log
    return base64.b64encode(pdf).decode("ascii"), None


# ---- Совместимость со старым кодом (если где-то ещё дергается) ----

def compile_latex_to_pdf_bytes(latex: str, timeout: int = 60) -> Tuple[Optional[bytes], str]:
    data = compile_latex(latex, timeout=timeout)
    if data is None:
        return None, "compile failed"
    return data, ""


