import os
import base64
import asyncio
import logging
from dotenv import load_dotenv

import fitz  # PyMuPDF: pip install pymupdf
from openai import OpenAI

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

# Инициализация OpenAI клиента
client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)


def sync_ocr(path_or_url: str) -> str:
    """
    Выполняет OCR через OpenAI Vision. Поддерживает:
      - URL изображений
      - Локальные JPG/PNG файлы
      - PDF-файлы (конвертирует первую страницу в PNG)

    Возвращает распознанный текст или пустую строку при отказе/ошибке.
    """
    # Подготовка данных изображения
    if path_or_url.startswith("http"):  # URL
        image_data = {"url": path_or_url, "detail": "high"}
    else:
        ext = os.path.splitext(path_or_url)[1].lower()
        # PDF → конвертация в PNG
        if ext == ".pdf":
            doc = fitz.open(path_or_url)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            mime = "png"
        else:
            with open(path_or_url, "rb") as f:
                img_bytes = f.read()
            # Определяем MIME по расширению
            mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip('.')
        # Кодируем в base64 и формируем data URI
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/{mime};base64,{b64}"
        image_data = {"url": data_uri, "detail": "high"}

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text",      "text": "Извлеките весь текст (русский, цифры, формулы) из этого изображения."},
                    {"type": "image_url", "image_url": image_data}
                ]
            }]
        )
        text = resp.choices[0].message.content.strip()
        low = text.lower()
        # Проверяем отказ
        if "извин" in low or "sorry" in low:
            logger.info("OCR отказ: %r", text)
            return ""
        logger.debug("OCR result: %r", text)
        return text

    except Exception as e:
        logger.exception("Ошибка при OCR: %s", e)
        return ""


async def ocr_openai_vision(path_or_url: str) -> str:
    """Асинхронная обёртка sync_ocr через asyncio.to_thread."""
    return await asyncio.to_thread(sync_ocr, path_or_url)


import base64, os, tempfile, logging

async def handle_ocr(task: dict) -> dict:
    """
    Принимает таск вида {
        type: "ocr",
        user_id: ...,
        student_id: ...,
        file_data: "<base64>",
        file_name: "...",
        prompt: "ваш промптом из подписи"
    }
    Выполняет OCR и возвращает dict с полем text и original prompt.
    """
    user_id    = task.get("user_id")
    student_id = task.get("student_id")
    prompt     = task.get("prompt", "").strip()

    # декодируем файл
    file_data = task.get("file_data")
    if not file_data:
        return {"type": "error", "user_id": user_id, "message": "Нет данных для OCR."}

    try:
        data = base64.b64decode(file_data)
    except Exception as e:
        logger.error("Ошибка base64 декодирования OCR-файла: %s", e)
        return {"type": "error", "user_id": user_id, "message": "Невалидные данные файла."}

    # сохраняем во временный файл
    suffix = os.path.splitext(task.get("file_name", "file"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    # запускаем OCR
    try:
        text = await ocr_openai_vision(tmp.name)
    except Exception as e:
        logger.exception("OCR failure")
        os.remove(tmp.name)
        return {"type": "error", "user_id": user_id, "message": "Ошибка OCR-сервиса."}
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    text = text.strip()
    if not text:
        return {"type": "error", "user_id": user_id, "message": "Не удалось распознать текст."}

    # возвращаем вместе с исходным prompt
    return {
        "type": "ocr",
        "user_id": user_id,
        "student_id": student_id,
        "text": text,
        "prompt": prompt
    }

from worker.services.tasks_service import handle_tasks


async def handle_ocr_and_generate(task: dict) -> dict:
    """
    Скачивает файл из task["file_data"], делает OCR, склеивает с task["prompt"]
    и сразу вызывает handle_tasks для генерации PDF.
    """
    user_id    = task.get("user_id")
    student_id = task.get("student_id")
    user_prompt = task.get("prompt", "").strip()

    # 1. Распаковываем base64
    try:
        data = base64.b64decode(task["file_data"])
    except Exception as e:
        logger.error("OCR+Gen: ошибка декодирования: %s", e)
        return {"type": "error", "user_id": user_id, "message": "Ошибка обработки файла."}

    # 2. Сохраняем во временный файл
    suffix = os.path.splitext(task.get("file_name", ""))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data); tmp.close()

    # 3. OCR
    try:
        text = await ocr_openai_vision(tmp.name)
    except Exception as e:
        logger.exception("OCR+Gen: ошибка OCR")
        os.remove(tmp.name)
        return {"type": "error", "user_id": user_id, "message": "Ошибка OCR."}
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    text = (text or "").strip()
    if not text:
        return {"type": "error", "user_id": user_id, "message": "Не удалось распознать текст."}

    # 4. Склеиваем финальный промпт
    final_prompt = f"{user_prompt}\n\n{text}" if user_prompt else text

    # 5. Вызываем генерацию напрямую
    gen_task = {
        "type": "generate_tasks",
        "user_id": user_id,
        "student_id": student_id,
        "prompt": final_prompt
    }
    return await handle_tasks(gen_task)