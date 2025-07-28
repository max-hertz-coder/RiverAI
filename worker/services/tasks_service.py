from worker.tasks import generate_tasks
import base64
import logging

logger = logging.getLogger(__name__)

async def handle_tasks(task: dict) -> dict:
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    prompt = task.get("prompt", "")
    instruction = task.get("instruction", "")
    generate_solutions = task.get("generate_solutions", True)

    if not prompt and not task.get("file_data"):
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Запрос для генерации заданий пуст."
        }

    payload = {
        "prompt": prompt,
        "instruction": instruction,
        "generate_solutions": generate_solutions
    }

    # если OCR
    if "file_data" in task and "filename" in task:
        import os, tempfile
        raw = base64.b64decode(task["file_data"])
        ext = task["filename"].split(".")[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as f:
            f.write(raw)
            f.flush()
            payload["use_ocr"] = True
            payload["path_or_url"] = f.name

    try:
        result = await generate_tasks.execute(payload)
    except Exception:
        logger.exception("Ошибка при выполнении generate_tasks")
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Ошибка генерации LaTeX или GPT"
        }

    text_summary = result.get("corrected_tasks") or result.get("raw_tasks", "")
    pdf_bytes = result.get("pdf_bytes")

    if not pdf_bytes:
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Не удалось собрать PDF-файл."
        }

    file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    return {
        "type": "tasks",
        "user_id": user_id,
        "student_id": student_id,
        "tasks_text": text_summary[:1500],  # для Telegram
        "file": file_b64,
    }
