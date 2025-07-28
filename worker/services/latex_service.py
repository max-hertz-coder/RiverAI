# worker/services/latex_service.py

import os
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

async def compile_latex_to_pdf(latex_source: str) -> bytes:
    """
    Компилирует LaTeX-код в PDF с поддержкой Unicode через XeLaTeX.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "document.tex")
        pdf_path = os.path.join(tmpdir, "document.pdf")

        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)

        try:
            subprocess.run(
                ["xelatex", "-interaction=nonstopmode", tex_path],
                cwd=tmpdir,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error("❌ Ошибка компиляции LaTeX: %s", e)
            raise

        with open(pdf_path, "rb") as f:
            return f.read()
