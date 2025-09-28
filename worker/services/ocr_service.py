# worker/services/ocr_service.py
from __future__ import annotations

import os
import base64
import tempfile
import logging
import asyncio
from importlib import import_module
from typing import Optional

import fitz  # PyMuPDF
from openai import OpenAI

from worker.services.tasks_service import handle_tasks

logger = logging.getLogger(__name__)

# -------- OpenAI Vision OCR (через Chat Completions) --------

def _pick_openai_key() -> str:
    keys: list[str] = []
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
        mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".") or "png"
    if len(img_bytes) > 20 * 1024 * 1024:
        raise ValueError("File too large for OCR")
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"

def sync_ocr(path_or_url: str) -> str:
    """
    OCR через OpenAI. Для моделей семейства gpt-5 используем temperature=1.0 и max_completion_tokens.
    """
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
                {"type": "text", "text": "Что написано на этом изображении? Ответ верните чистым текстом без комментариев."},
                {"type": "image_url", "image_url": image_data},
            ],
        }],
        temperature=1.0,              # ⟵ важно для gpt-5
        max_completion_tokens=2000,
    )
    text = (resp.choices[0].message.content or "").strip()
    low = text.lower()
    if any(x in low for x in ("извин", "sorry", "can't", "не могу", "cannot")):
        return ""
    return text

async def ocr_openai_vision(path_or_url: str) -> str:
    return await asyncio.to_thread(sync_ocr, path_or_url)

# -------- Альтернативный OCR (PIL + pytesseract), динамические импорты --------

def _alt_ocr_image_bytes(data: bytes) -> str:
    """
    Альтернативный OCR через PIL + pytesseract.
    Импортируем модули динамически, чтобы не падал линтер/рантайм, если пакетов нет.
    """
    try:
        pil_mod = import_module("PIL.Image")
        pyt_mod = import_module("pytesseract")
    except Exception:
        return ""

    from io import BytesIO
    try:
        img = pil_mod.open(BytesIO(data))
        text = pyt_mod.image_to_string(img, lang="rus+eng")
        return (text or "").strip()
    except Exception:
        return ""

# -------- Входные обработчики задач --------

async def handle_ocr(task: dict) -> dict:
    """
    task = { task_id: str, file_data: base64, file_name: str, prompt?: str }
    """
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "task_id": None, "message": "Нет task_id."}

    file_b64 = task.get("file_data")
    if not file_b64:
        return {"type": "error", "task_id": task_id, "message": "Нет данных файла."}

    try:
        data = base64.b64decode(file_b64)
    except Exception:
        return {"type": "error", "task_id": task_id, "message": "Невалидные данные файла (base64)."}

    suffix = os.path.splitext(task.get("file_name", "file.jpg"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.flush()
    tmp.close()

    try:
        text = (await ocr_openai_vision(tmp.name) or "").strip()
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    if not text:
        # Фолбэк: попробуем tesseract, если установлен
        text = _alt_ocr_image_bytes(data)

    if not text:
        return {"type": "error", "task_id": task_id, "message": "Не удалось распознать текст."}

    return {
        "type": "ocr",
        "task_id": task_id,
        "text": text,
        "prompt": (task.get("prompt") or "").strip(),
    }

async def handle_ocr_and_generate(task: dict) -> dict:
    """
    OCR -> генерация заданий (единый pipeline).
    """
    task_id = task.get("task_id")
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    file_b64 = task.get("file_data")
    if not file_b64:
        return {"type": "error", "task_id": task_id, "message": "Нет данных файла."}

    try:
        data = base64.b64decode(file_b64)
    except Exception:
        return {"type": "error", "task_id": task_id, "message": "Ошибка обработки файла."}

    suffix = os.path.splitext(task.get("file_name", "file.jpg"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.flush()
    tmp.close()

    try:
        ocr_text = (await ocr_openai_vision(tmp.name) or "").strip()
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass

    if not ocr_text:
        return {"type": "error", "task_id": task_id, "message": "Не удалось распознать текст."}

    user_prompt = (task.get("prompt") or "").strip()
    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

    gen_task = {"task_id": task_id, "type": "generate_tasks", "prompt": final_prompt}
    result = await handle_tasks(gen_task)  # уже включает PDF base64
    result["prompt"] = final_prompt
    return result
