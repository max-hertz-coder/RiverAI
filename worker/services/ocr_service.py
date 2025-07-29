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
    user_id = task.get("user_id")
    # Determine input source
    image_path = None
    try:
        if task.get("url"):
            image_path = task["url"]
        elif task.get("file_data"):
            # Decode base64 file data
            file_bytes = base64.b64decode(task["file_data"])
            # Determine extension by simple signature inspection
            ext = ".jpg"
            if file_bytes[:4] == b"%PDF":
                ext = ".pdf"
            elif file_bytes[:4] == b"\x89PNG":
                ext = ".png"
            elif file_bytes[:2] == b"\xff\xd8":  # JPEG
                ext = ".jpg"
            # Write to temp file
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp_file.write(file_bytes)
            tmp_file.close()
            image_path = tmp_file.name
        else:
            return {"type": "error", "user_id": user_id, "message": "Нет изображения для OCR."}

        # Perform OCR
        text = await ocr_openai_vision(image_path)
        # Clean up temp file if used
        if image_path and not image_path.startswith("http"):
            os.remove(image_path)
    except Exception as e:
        logging.exception("Ошибка OCR: %s", e)
        return {"type": "error", "user_id": user_id, "message": "Ошибка при распознавании текста."}

    # If OCR yields no text (e.g., Vision API refusal or blank image)
    if not text or text.strip() == "":
        return {"type": "error", "user_id": user_id, "message": "Не удалось распознать текст на изображении."}

    # Success
    return {
        "type": "ocr",
        "user_id": user_id,
        "text": text.strip()
    }