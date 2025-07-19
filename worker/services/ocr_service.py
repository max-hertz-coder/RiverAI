import os
import base64
import logging
import asyncio
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEYS"))

logger = logging.getLogger(__name__)

def _sync_ocr(path_or_url: str) -> str:
    """
    Синхронная OCR-обработка через OpenAI Vision.
    """
    if path_or_url.startswith("data:") or path_or_url.startswith("http"):
        image_obj = {"url": path_or_url, "detail": "high"}
    else:
        with open(path_or_url, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        image_obj = {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Извлеките текст из этого изображения."},
                    {"type": "image_url", "image_url": image_obj}
                ]
            }]
        )
        text = resp.choices[0].message.content.strip()
        low = text.lower()
        if "извин" in low or "sorry" in low:
            logger.info("OCR отказ: %r", text)
            return ""
        return text
    except Exception as e:
        logger.exception("Ошибка при OCR: %s", e)
        return ""

async def ocr_openai_vision(path_or_url: str) -> str:
    return await asyncio.to_thread(_sync_ocr, path_or_url)
