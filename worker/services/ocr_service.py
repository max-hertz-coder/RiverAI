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

logger = logging.getLogger(__name__)

# =========================================================
# Настройки и выбор ключа OpenAI
# =========================================================

def _pick_openai_key() -> str:
    """
    Берёт ключ из OPENAI_API_KEYS (через запятую/переводы строки) или OPENAI_API_KEY.
    Возвращает первый валидный ключ.
    """
    keys: list[str] = []
    raw = (os.getenv("OPENAI_API_KEYS") or "") + "," + (os.getenv("OPENAI_API_KEY") or "")
    for k in raw.replace("\n", ",").split(","):
        k = k.strip()
        if k:
            keys.append(k)
    for k in keys:
        if k and len(k) > 20:
            return k
    raise RuntimeError("Missing OPENAI_API_KEY/OPENAI_API_KEYS environment variable")

OPENAI_KEY = _pick_openai_key()
_client = OpenAI(api_key=OPENAI_KEY)

# Модели для OCR-vision: сначала самая быстрая/надёжная, далее фолбэки
_VISION_MODELS = [
    "gpt-4o",        # быстрый и качественный vision
    "gpt-4o-mini",   # ещё быстрее, если доступен
    "gpt-5",         # fallback (требует temperature=1.0 и max_completion_tokens)
]


# =========================================================
# Утилиты для конвертации входных файлов в data-uri
# =========================================================

def _pdf_to_png_bytes(path: str) -> bytes:
    """
    Рендерим первую страницу PDF в PNG (dpi=300), чтобы передать в vision.
    """
    doc = fitz.open(path)
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=300)
        data = pix.tobytes("png")
        return data
    finally:
        doc.close()

def _to_data_uri(path: str) -> str:
    """
    В путь может прийти pdf/jpg/png/... Превращаем в data:image/...;base64,...
    """
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext == ".pdf":
        img_bytes = _pdf_to_png_bytes(path)
        mime = "png"
    else:
        with open(path, "rb") as f:
            img_bytes = f.read()
        mime = "jpeg" if ext in (".jpg", ".jpeg") else (ext.lstrip(".") or "png")

    if len(img_bytes) > 20 * 1024 * 1024:
        raise ValueError("File too large for OCR (>20MB)")

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"


# =========================================================
# Синхронный визион-вызов (оборачиваем в executor)
# =========================================================

def _sync_vision_ocr(path_or_url: str) -> str:
    """
    OCR через OpenAI Chat Completions с image_url.
    Перебираем модели в порядке приоритета, пока не получим непустой текст.
    Для семейств gpt-5 — строго temperature=1.0 и max_completion_tokens.
    """
    logger.info("🔧 OCR: %s", path_or_url)

    if path_or_url.startswith("http"):
        image_data = {"url": path_or_url, "detail": "high"}
    else:
        image_data = {"url": _to_data_uri(path_or_url), "detail": "high"}

    last_err: Optional[Exception] = None

    for model in _VISION_MODELS:
        try:
            kwargs = dict(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Распознай текст на изображении. Верни ТОЛЬКО чистый текст без комментариев."},
                        {"type": "image_url", "image_url": image_data},
                    ],
                }],
            )
            # Особенности семейств gpt-5
            if model.startswith("gpt-5"):
                kwargs.update(dict(temperature=1.0, max_completion_tokens=2000))
            else:
                kwargs.update(dict(temperature=0.2, max_tokens=2000))

            resp = _client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()

            # фильтруем "извините/не могу"
            low = text.lower()
            if not text or any(x in low for x in ("извин", "sorry", "can't", "cannot", "не могу")):
                raise RuntimeError("empty_or_refusal")

            return text

        except Exception as e:
            last_err = e
            logger.warning("⚠️ Vision OCR failed on model=%s: %s", model, e)

    if last_err:
        raise last_err
    return ""


async def ocr_openai_vision(path_or_url: str) -> str:
    """
    Неблокирующий OCR: выносим синхронный вызов клиента в пул потоков.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_vision_ocr, path_or_url)


# =========================================================
# Альтернативный OCR: PIL + pytesseract (динамический импорт)
# =========================================================

def _alt_ocr_image_bytes(data: bytes) -> str:
    """
    Фолбэк OCR через PIL+pytesseract.
    Импортируем модули динамически, чтобы код работал даже если пакетов нет.
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


# =========================================================
# Входные обработчики задач
# =========================================================

async def handle_ocr(task: dict) -> dict:
    """
    task = { task_id: str, file_data: base64, file_name: str, prompt?: str }
    Распознаём файл -> возвращаем {type:"ocr", text, prompt?}
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
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()

        text = (await ocr_openai_vision(tmp.name) or "").strip()
        if not text:
            # Фолбэк на тессеракт (если установлен)
            text = _alt_ocr_image_bytes(data)

    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

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
    OCR -> генерация заданий (единый быстрый pipeline).
    ВАЖНО: генерацию делаем одним батчем в сервисе задач (для скорости).
    """
    from worker.services.tasks_service import handle_tasks  # локальный импорт, чтобы избежать циклических

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
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()

        ocr_text = (await ocr_openai_vision(tmp.name) or "").strip()
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass

    if not ocr_text:
        # Попытка фолбэком
        ocr_text = _alt_ocr_image_bytes(data)

    if not ocr_text:
        return {"type": "error", "task_id": task_id, "message": "Не удалось распознать текст."}

    user_prompt = (task.get("prompt") or "").strip()
    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

    gen_task = {"task_id": task_id, "type": "generate_tasks", "prompt": final_prompt}
    result = await handle_tasks(gen_task)  # внутри — генерация батчем + PDF в base64
    result["prompt"] = final_prompt
    return result
