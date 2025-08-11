# worker/services/ocr_service.py
import os
import base64
import tempfile
import logging
import asyncio

import fitz  # PyMuPDF
from openai import OpenAI

from worker.services.tasks_service import handle_tasks

def _pick_openai_key() -> str:
    keys = []
    raw = (os.getenv("OPENAI_API_KEYS") or "") + "," + (os.getenv("OPENAI_API_KEY") or "")
    for k in raw.replace("\n", ",").split(","):
        k = k.strip()
        if k:
            keys.append(k)
    if not keys:
        raise RuntimeError("Missing OPENAI_API_KEY/OPENAI_API_KEYS environment variable")
    return keys[0]

OPENAI_KEY = _pick_openai_key()
client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

def _pdf_to_png_bytes(path: str) -> bytes:
    doc = fitz.open(path)
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300)
    data = pix.tobytes("png")
    doc.close()
    return data

def _to_data_uri(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        img_bytes = _pdf_to_png_bytes(path)
        mime = "png"
    else:
        with open(path, "rb") as f:
            img_bytes = f.read()
        mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
    if len(img_bytes) > 20 * 1024 * 1024:
        raise ValueError("File too large for OCR")
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"

def sync_ocr(path_or_url: str) -> str:
    logger.info("🔧 OCR: %s", path_or_url)
    if path_or_url.startswith("http"):
        image_data = {"url": path_or_url, "detail": "high"}
    else:
        image_data = {"url": _to_data_uri(path_or_url), "detail": "high"}

    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Что написано на этом изображении? Ответ — просто текст."},
                {"type": "image_url", "image_url": image_data},
            ],
        }],
        temperature=0.0,
        # gpt-5* требует max_completion_tokens
        max_completion_tokens=4000,
    )
    text = (resp.choices[0].message.content or "").strip()
    low = text.lower()
    if any(x in low for x in ("извин", "sorry", "can't", "не могу")):
        return ""
    if text in ("НЕТЕКСТ", "НЕТЕКСТ."):
        return ""
    return text

async def ocr_openai_vision(path_or_url: str) -> str:
    return await asyncio.to_thread(sync_ocr, path_or_url)

async def handle_ocr(task: dict) -> dict:
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    file_data = task.get("file_data")
    if not file_data:
        return {"type": "error", "task_id": task_id, "message": "Нет данных для OCR."}

    try:
        data = base64.b64decode(file_data)
    except Exception:
        return {"type": "error", "task_id": task_id, "message": "Невалидные данные файла."}

    suffix = os.path.splitext(task.get("file_name", "file.jpg"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data); tmp.close()

    try:
        text = (await ocr_openai_vision(tmp.name) or "").strip()
    finally:
        try: os.remove(tmp.name)
        except Exception: pass

    if not text:
        return {"type": "error", "task_id": task_id, "message": "Не удалось распознать текст."}

    return {
        "type": "ocr",
        "task_id": task_id,
        "text": text,
        "prompt": (task.get("prompt") or "").strip(),
    }

async def handle_ocr_and_generate(task: dict) -> dict:
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    try:
        data = base64.b64decode(task["file_data"])
    except Exception:
        return {"type": "error", "task_id": task_id, "message": "Ошибка обработки файла."}

    suffix = os.path.splitext(task.get("file_name", "file.jpg"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data); tmp.close()

    try:
        ocr_text = (await ocr_openai_vision(tmp.name) or "").strip()
    finally:
        try: os.remove(tmp.name)
        except Exception: pass

    if not ocr_text:
        return {"type": "error", "task_id": task_id, "message": "Не удалось распознать текст."}

    user_prompt = (task.get("prompt") or "").strip()
    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

    gen_task = {"task_id": task_id, "type": "generate_tasks", "prompt": final_prompt}
    result = await handle_tasks(gen_task)  # уже с PDF base64
    result["prompt"] = final_prompt
    return result
