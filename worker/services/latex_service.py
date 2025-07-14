import subprocess
import tempfile
import os

# Paths to LaTeX templates (if needed)
PLAN_TEMPLATE_PATH = "templates/plan_template.tex"
TASKS_TEMPLATE_PATH = "templates/tasks_template.tex"
REPORT_TEMPLATE_PATH = "templates/report_template.tex"

def generate_plan_pdf(plan_text: str) -> str:
    """
    Generate a PDF for the study plan. Returns the file path or None if failed.
    """
    # Simple LaTeX generation: embed plan_text into a basic template
    latex_content = r"\documentclass{article}\begin{document}" + "\n"
    latex_content += plan_text.replace('%', '\%') + "\n"  # escape %
    latex_content += r"\end{document}"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "plan.tex")
            pdf_path = os.path.join(tmpdir, "plan.pdf")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_content)
            # Run pdflatex
            result = subprocess.run(["pdflatex", "-interaction=batchmode", tex_path], cwd=tmpdir, capture_output=True)
            if result.returncode == 0 and os.path.exists(pdf_path):
                # Copy PDF out of temp dir (since it will be cleaned up)
                final_path = os.path.join(os.getcwd(), f"plan_{os.getpid()}.pdf")
                os.replace(pdf_path, final_path)
                return final_path
    except Exception as e:
        print(f"PDF generation error: {e}")
    return None

def generate_tasks_pdf(tasks_parts: list) -> str:
    """
    Generate PDF for tasks. tasks_parts is list of alternating task and solution texts.
    """
    latex_content = r"\documentclass{article}\usepackage{enumitem}\begin{document}\section*{Сгенерированные задания}" + "\n"
    latex_content += r"\begin{enumerate}[leftmargin=*]" + "\n"
    for i in range(0, len(tasks_parts), 2):
        task = tasks_parts[i].strip()
        latex_content += r"\item " + task.replace('%', '\%') + "\n"
        if i+1 < len(tasks_parts):
            solution = tasks_parts[i+1].strip()
            latex_content += r"\newline \textbf{Решение:} " + solution.replace('%', '\%') + "\n"
    latex_content += r"\end{enumerate}\end{document}"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "tasks.tex")
            pdf_path = os.path.join(tmpdir, "tasks.pdf")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_content)
            result = subprocess.run(["pdflatex", "-interaction=batchmode", tex_path], cwd=tmpdir, capture_output=True)
            if result.returncode == 0 and os.path.exists(pdf_path):
                final_path = os.path.join(os.getcwd(), f"tasks_{os.getpid()}.pdf")
                os.replace(pdf_path, final_path)
                return final_path
    except Exception as e:
        print(f"PDF generation error: {e}")
    return None

def generate_report_pdf(report_text: str) -> str:
    """
    Generate PDF for homework check report.
    """
    latex_content = r"\documentclass{article}\begin{document}\section*{Отчёт проверки}" + "\n"
    latex_content += report_text.replace('%', '\%') + "\n"
    latex_content += r"\end{document}"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "report.tex")
            pdf_path = os.path.join(tmpdir, "report.pdf")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_content)
            result = subprocess.run(["pdflatex", "-interaction=batchmode", tex_path], cwd=tmpdir, capture_output=True)
            if result.returncode == 0 and os.path.exists(pdf_path):
                final_path = os.path.join(os.getcwd(), f"report_{os.getpid()}.pdf")
                os.replace(pdf_path, final_path)
                return final_path
    except Exception as e:
        print(f"PDF generation error: {e}")
    return None
