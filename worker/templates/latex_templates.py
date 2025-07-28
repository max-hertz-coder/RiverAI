# worker/templates/latex_templates.py

LATEX_TEMPLATE = r"""
\documentclass[12pt]{article}
\usepackage{fontspec}
\usepackage{polyglossia}
\setmainlanguage{russian}
\setmainfont{Times New Roman}
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
