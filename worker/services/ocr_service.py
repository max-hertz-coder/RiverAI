import os
import asyncio
import logging
import fitz  # PyMuPDF: pip install pymupdf
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем окружение и инициализируем клиента
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")
client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

def sync_ocr(path_or_url: str) -> str:
    """
    Выполняет OCR через OpenAI Vision. Поддерживает URL, локальные JPG/PNG и PDF.
    Возвращает распознанный текст или пустую строку при отказе/ошибке.
    """
    try:
        # Подготовка данных изображения
        if path_or_url.startswith("http"):
            image_data = {"url": path_or_url, "detail": "high"}
        else:
            ext = os.path.splitext(path_or_url)[1].lower()
            if ext == ".pdf":
                doc = fitz.open(path_or_url)
                pix = doc.load_page(0).get_pixmap(dpi=300)
                image_data = {"bytes": pix.tobytes("png"), "detail": "high"}
            else:
                with open(path_or_url, "rb") as f:
                    image_data = {"bytes": f.read(), "detail": "high"}

        # Запрос к OpenAI Vision
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Извлеките весь текст (русский, цифры, формулы) из этого изображения."},
                    {"type": "image_url", "image_url": image_data}
                ]
            }]
        )
        text = resp.choices[0].message.content.strip()
        low = text.lower()
        if "извин" in low or "sorry" in low:
            logger.info("OCR отказ: %r", text)
            return ""
        logger.debug("OCR result: %r", text)
        return text
    except Exception as e:
        logger.exception("Ошибка при OCR: %s", e)
        return ""


async def ocr_openai_vision(path_or_url: str) -> str:
    """
    Асинхронная обёртка для sync_ocr через asyncio.to_thread.
    """
    return await asyncio.to_thread(sync_ocr, path_or_url)