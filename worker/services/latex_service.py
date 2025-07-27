import os
import subprocess
import tempfile

async def compile_latex_to_pdf(latex_source: str) -> bytes:
    """
    Компилирует LaTeX-код в PDF и возвращает байты файла.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = os.path.join(tmpdir, "document.tex")
        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(latex_source)
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            cwd=tmpdir,
            check=True
        )
        pdf_path = os.path.join(tmpdir, "document.pdf")
        with open(pdf_path, "rb") as f:
            return f.read()